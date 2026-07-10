import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Import MoviePy 2.x classes directly from package
try:
    from moviepy import VideoFileClip, ImageClip, ColorClip, CompositeVideoClip, AudioFileClip, AudioClip, vfx
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, AudioLoop
except ImportError as e:
    print(f"Error importing MoviePy 2.x: {e}")
    VideoFileClip = None
    ImageClip = None
    ColorClip = None
    CompositeVideoClip = None
    AudioFileClip = None
    AudioClip = None
    vfx = None
    AudioFadeIn = None
    AudioFadeOut = None
    AudioLoop = None

try:
    from proglog import ProgressBarLogger
except ImportError:
    ProgressBarLogger = object


class CustomMoviePyLogger(ProgressBarLogger):
    """Custom MoviePy logger that reports progress updates to a callback."""
    def __init__(self, task_id, progress_callback):
        super().__init__()
        self.task_id = task_id
        self.progress_callback = progress_callback
        self.total_frames = 0
        self.current_frame = 0

    def bars_callback(self, bar, attr, value, old_value=None):
        if bar == 't':
            total = self.bars[bar].get('total', 1)
            if total > 0:
                percentage = int((value / total) * 100)
                percentage = min(max(percentage, 0), 100)
                self.progress_callback(
                    self.task_id, 
                    percentage, 
                    f"正在渲染影片影格: {value}/{total} ({percentage}%)"
                )


def wrap_text(text, font, max_width):
    """Wrap text to fit within a maximum width in pixels, supporting English and Chinese character wrapping."""
    lines = []
    current_line = ""
    i = 0
    while i < len(text):
        test_line = current_line + text[i]
        try:
            if hasattr(font, 'getbbox'):
                w = font.getbbox(test_line)[2]
            else:
                w = font.getsize(test_line)[0]
        except Exception:
            w = len(test_line) * 20 * 0.6  # basic fallback estimation
            
        if w <= max_width:
            current_line = test_line
            i += 1
        else:
            if current_line:
                lines.append(current_line)
                current_line = ""
            else:
                lines.append(text[i])
                i += 1
    if current_line:
        lines.append(current_line)
    return lines


def draw_wrapped_text_centered(draw, text, font, y_start, max_width, screen_width, is_top=True):
    """Draws multi-line wrapped text centered horizontally."""
    lines = wrap_text(text, font, max_width)
    line_heights = []
    for line in lines:
        try:
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(line)
                h = bbox[3] - bbox[1]
            else:
                h = font.getsize(line)[1]
        except Exception:
            h = 40
        line_heights.append(h)
        
    total_height = sum(line_heights) + (len(lines) - 1) * 10
    
    if is_top:
        current_y = y_start
    else:
        current_y = y_start - total_height
        
    for i, line in enumerate(lines):
        try:
            if hasattr(font, 'getbbox'):
                w = font.getbbox(line)[2]
            else:
                w = font.getsize(line)[0]
        except Exception:
            w = len(line) * 30
        x = (screen_width - w) // 2
        
        # White text with black outline for visibility
        draw.text(
            (x, current_y), 
            line, 
            fill=(255, 255, 255, 255), 
            font=font, 
            stroke_width=4, 
            stroke_fill=(0, 0, 0, 255)
        )
        current_y += line_heights[i] + 10


def create_text_clip(text, width, height, font_size=40, font_color=(255, 255, 255, 255), duration=3.0):
    """Creates a transparent ImageClip overlay with centered text using Pillow."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Try to load default bold system fonts
    font = None
    font_names = []
    if sys.platform.startswith("win"):
        font_names = ["msjhbd.ttc", "msjh.ttc", "arialbd.ttf", "arial.ttf", "simsun.ttc"]
    elif sys.platform.startswith("darwin"):
        font_names = ["/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial.ttf"]
    else:
        font_names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        
    for fn in font_names:
        try:
            font = ImageFont.truetype(fn, font_size)
            break
        except Exception:
            continue
    if not font:
        font = ImageFont.load_default()
        
    draw_wrapped_text_centered(draw, text, font, height // 2 - font_size // 2, int(width * 0.9), width, is_top=True)
    
    img_array = np.array(image)
    rgb_array = img_array[:, :, :3]
    alpha_array = img_array[:, :, 3] / 255.0
    
    mask = ImageClip(alpha_array, is_mask=True).with_duration(duration)
    clip = ImageClip(rgb_array).with_mask(mask).with_duration(duration)
    return clip


def process_slideshow_image(img_path, width=1280, height=720):
    """Resize image preserving aspect ratio and paste centered on a black background."""
    with Image.open(img_path) as img:
        img = img.convert("RGBA")
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        bg = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        offset = ((width - img.width) // 2, (height - img.height) // 2)
        bg.paste(img, offset, img)
        return bg.convert("RGB")


def generate_slideshow_video(task_id, images_paths, title, bg_music_path, output_path, progress_callback):
    """Generate a slideshow from images with transitions, title overlay, and background music."""
    progress_callback(task_id, 10, "正在讀取並處理圖片...")
    
    img_dur = 3.0
    fade_dur = 0.5
    clips = []
    
    for i, path in enumerate(images_paths):
        img = process_slideshow_image(path)
        clip = ImageClip(np.array(img)).with_duration(img_dur + fade_dur)
        if i > 0:
            clip = clip.with_effects([vfx.FadeIn(fade_dur)])
        clip = clip.with_start(i * img_dur)
        clips.append(clip)
        
    progress_callback(task_id, 30, "正在合成投影片軌道...")
    video = CompositeVideoClip(clips)
    total_dur = len(images_paths) * img_dur + fade_dur
    video = video.with_duration(total_dur)
    
    # Title Overlay
    if title:
        title_clip = create_text_clip(title, 1280, 720, font_size=55, duration=3.0)
        title_clip = title_clip.with_start(0.5).with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
        video = CompositeVideoClip([video, title_clip]).with_duration(total_dur)
        
    # Background Music
    if bg_music_path and os.path.exists(bg_music_path):
        progress_callback(task_id, 45, "正在處理背景音樂...")
        try:
            audio = AudioFileClip(bg_music_path)
            if audio.duration < total_dur:
                audio = audio.with_effects([AudioLoop(duration=total_dur)])
            else:
                audio = audio.subclipped(0, total_dur)
            audio = audio.with_effects([AudioFadeOut(1.0)])
            video = video.with_audio(audio)
        except Exception as e:
            print(f"Error adding audio: {e}")
            
    progress_callback(task_id, 60, "正在渲染影片並寫入檔案...")
    logger = CustomMoviePyLogger(task_id, progress_callback)
    
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=logger
    )
    
    # Close clips
    video.close()
    for c in clips:
        c.close()
    progress_callback(task_id, 100, "影片生成完成！")


def create_meme_overlay(top_text, bottom_text, width=1280, height=720, duration=5.0):
    """Create a transparent overlay containing meme text at the top and bottom."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    font = None
    font_size = 55
    font_names = []
    if sys.platform.startswith("win"):
        font_names = ["impact.ttf", "arialbd.ttf", "msjhbd.ttc", "arial.ttf", "simsun.ttc"]
    elif sys.platform.startswith("darwin"):
        font_names = ["/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/PingFang.ttc"]
    else:
        font_names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        
    for fn in font_names:
        try:
            font = ImageFont.truetype(fn, font_size)
            break
        except Exception:
            continue
    if not font:
        font = ImageFont.load_default()
        
    max_w = int(width * 0.95)
    if top_text:
        draw_wrapped_text_centered(draw, top_text, font, 30, max_w, width, is_top=True)
    if bottom_text:
        draw_wrapped_text_centered(draw, bottom_text, font, height - 30, max_w, width, is_top=False)
        
    img_array = np.array(image)
    rgb_array = img_array[:, :, :3]
    alpha_array = img_array[:, :, 3] / 255.0
    
    mask = ImageClip(alpha_array, is_mask=True).with_duration(duration)
    clip = ImageClip(rgb_array).with_mask(mask).with_duration(duration)
    return clip


def generate_meme_video(task_id, video_path, top_text, bottom_text, output_path, progress_callback):
    """Overlay meme captions on top of a user-uploaded video, fitting to a standard 1280x720 frame."""
    progress_callback(task_id, 10, "正在讀取影片檔案...")
    
    clip = VideoFileClip(video_path)
    duration = min(clip.duration, 15.0)
    clip = clip.subclipped(0, duration)
    
    progress_callback(task_id, 30, "正在縮放並居中影片影格...")
    clip_resized = clip.resized(height=720)
    if clip_resized.w > 1280:
        clip_resized = clip_resized.resized(width=1280)
        
    bg_clip = ColorClip(size=(1280, 720), color=(0, 0, 0)).with_duration(duration)
    video = CompositeVideoClip([bg_clip, clip_resized.with_position("center")])
    
    progress_callback(task_id, 50, "正在繪製並加入迷因字幕...")
    text_overlay = create_meme_overlay(top_text, bottom_text, 1280, 720, duration)
    video = CompositeVideoClip([video, text_overlay]).with_duration(duration)
    
    if clip.audio is not None:
        video = video.with_audio(clip.audio)
        
    progress_callback(task_id, 65, "正在進行迷因影片編碼...")
    logger = CustomMoviePyLogger(task_id, progress_callback)
    
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=logger
    )
    
    video.close()
    clip.close()
    progress_callback(task_id, 100, "迷因影片生成完成！")


def create_brand_text_overlay(brand_name, tagline, duration=5.0):
    """Draw brand name and tagline on a transparent 1280x720 canvas."""
    image = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    brand_font = None
    brand_size = 50
    tagline_font = None
    tagline_size = 28
    
    font_names = []
    if sys.platform.startswith("win"):
        font_names = ["msjhbd.ttc", "arialbd.ttf", "simsun.ttc"]
    elif sys.platform.startswith("darwin"):
        font_names = ["/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial.ttf"]
    else:
        font_names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        
    for fn in font_names:
        try:
            brand_font = ImageFont.truetype(fn, brand_size)
            tagline_font = ImageFont.truetype(fn, tagline_size)
            break
        except Exception:
            continue
    if not brand_font:
        brand_font = ImageFont.load_default()
        tagline_font = ImageFont.load_default()
        
    if brand_name:
        try:
            if hasattr(brand_font, 'getbbox'):
                w = brand_font.getbbox(brand_name)[2]
            else:
                w = brand_font.getsize(brand_name)[0]
        except Exception:
            w = len(brand_name) * brand_size * 0.6
        x = (1280 - w) // 2
        # White text
        draw.text((x, 460), brand_name, fill=(255, 255, 255, 255), font=brand_font)
        
    if tagline:
        try:
            if hasattr(tagline_font, 'getbbox'):
                w = tagline_font.getbbox(tagline)[2]
            else:
                w = tagline_font.getsize(tagline)[0]
        except Exception:
            w = len(tagline) * tagline_size * 0.6
        x = (1280 - w) // 2
        # Gray text
        draw.text((x, 525), tagline, fill=(200, 200, 200, 255), font=tagline_font)
        
    img_array = np.array(image)
    rgb_array = img_array[:, :, :3]
    alpha_array = img_array[:, :, 3] / 255.0
    
    mask = ImageClip(alpha_array, is_mask=True).with_duration(duration)
    clip = ImageClip(rgb_array).with_mask(mask).with_duration(duration)
    return clip


def process_logo_canvas(logo_path, width=1280, height=720):
    """Resize logo image and center it on a transparent canvas, shifted up slightly."""
    with Image.open(logo_path) as img:
        img = img.convert("RGBA")
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offset = ((width - img.width) // 2, (height - img.height) // 2 - 60)
        canvas.paste(img, offset, img)
        return canvas


def generate_logo_intro_video(task_id, logo_path, brand_name, tagline, bg_music_path, output_path, progress_callback):
    """Generate a high-quality logo intro animation with brand text and sweep audio."""
    progress_callback(task_id, 10, "正在加載並處理 Logo 圖片...")
    
    # 5.0 seconds duration
    bg = ColorClip(size=(1280, 720), color=(15, 20, 35)).with_duration(5.0)
    
    logo_canvas = process_logo_canvas(logo_path)
    img_arr = np.array(logo_canvas)
    rgb_arr = img_arr[:, :, :3]
    alpha_arr = img_arr[:, :, 3] / 255.0
    
    logo_mask = ImageClip(alpha_arr, is_mask=True).with_duration(5.0)
    logo_clip = ImageClip(rgb_arr).with_mask(logo_mask).with_duration(5.0)
    
    # Apply zoom and fade in to logo
    logo_clip = logo_clip.resized(lambda t: 0.85 + 0.04 * t).with_effects([vfx.FadeIn(1.0)])
    
    progress_callback(task_id, 35, "正在渲染品牌文字...")
    text_clip = create_brand_text_overlay(brand_name, tagline, duration=5.0)
    # Starts at 1.2s and fades in
    text_clip = text_clip.with_start(1.2).with_effects([vfx.FadeIn(0.8)])
    
    video = CompositeVideoClip([bg, logo_clip, text_clip]).with_duration(5.0)
    
    if bg_music_path and os.path.exists(bg_music_path):
        progress_callback(task_id, 50, "正在載入音效並混合...")
        try:
            audio = AudioFileClip(bg_music_path)
            audio = audio.subclipped(0, 5.0).with_effects([AudioFadeOut(1.0)])
            video = video.with_audio(audio)
        except Exception as e:
            print(f"Error loading intro audio: {e}")
            
    progress_callback(task_id, 65, "正在編碼片頭影片...")
    logger = CustomMoviePyLogger(task_id, progress_callback)
    
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=logger
    )
    
    video.close()
    progress_callback(task_id, 100, "品牌片頭生成完成！")


def process_promo_image(img_path, width=720, height=1280):
    """Resize image preserving aspect ratio and crop the center to fill a 720x1280 frame."""
    with Image.open(img_path) as img:
        img = img.convert("RGBA")
        target_ratio = width / height
        img_ratio = img.width / img.height
        
        if img_ratio > target_ratio:
            new_height = height
            new_width = int(img.width * (height / img.height))
        else:
            new_width = width
            new_height = int(img.height * (width / img.width))
            
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        right = left + width
        bottom = top + height
        
        img_cropped = img_resized.crop((left, top, right, bottom))
        return img_cropped.convert("RGB")


def create_promo_text_overlay(brand_name, product_name, highlight, cta, width=720, height=1280, duration=2.5):
    """Creates a transparent ImageClip overlay with centered portrait text and bottom gradient overlay using Pillow."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    font_bold = None
    font_reg = None
    font_names = []
    if sys.platform.startswith("win"):
        font_names = ["msjhbd.ttc", "msjh.ttc", "arialbd.ttf", "arial.ttf", "simsun.ttc"]
    elif sys.platform.startswith("darwin"):
        font_names = ["/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial.ttf"]
    else:
        font_names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        
    for fn in font_names:
        try:
            font_bold = ImageFont.truetype(fn, 44)
            font_reg = ImageFont.truetype(fn, 26)
            break
        except Exception:
            continue
    if not font_bold:
        font_bold = ImageFont.load_default()
        font_reg = ImageFont.load_default()
        
    # Draw soft dark transparent gradient at the bottom 530px
    for y in range(750, 1280):
        # Scale alpha smoothly from 0 at y=750 to 180 at bottom
        alpha = int(((y - 750) / 530) * 180)
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        
    if brand_name and product_name:
        # Brand text (centered, y=890)
        try:
            if hasattr(font_reg, 'getbbox'):
                w_b = font_reg.getbbox(brand_name)[2]
            else:
                w_b = font_reg.getsize(brand_name)[0]
        except Exception:
            w_b = len(brand_name) * 26 * 0.6
        draw.text(((width - w_b) // 2, 890), brand_name, fill=(210, 210, 210, 255), font=font_reg)
        
        # Product Name (centered, y=950)
        try:
            if hasattr(font_bold, 'getbbox'):
                w_p = font_bold.getbbox(product_name)[2]
            else:
                w_p = font_bold.getsize(product_name)[0]
        except Exception:
            w_p = len(product_name) * 44 * 0.6
        draw.text(((width - w_p) // 2, 950), product_name, fill=(255, 255, 255, 255), font=font_bold)
        
    elif highlight:
        # Highlight text (centered, y=940)
        try:
            if hasattr(font_bold, 'getbbox'):
                w_h = font_bold.getbbox(highlight)[2]
            else:
                w_h = font_bold.getsize(highlight)[0]
        except Exception:
            w_h = len(highlight) * 44 * 0.6
            
        # Draw a tiny accent bar under the highlight text
        h_y = 940
        draw.text(((width - w_h) // 2, h_y), highlight, fill=(255, 255, 255, 255), font=font_bold)
        draw.line([((width - w_h) // 2, h_y + 65), ((width + w_h) // 2, h_y + 65)], fill=(139, 92, 246, 255), width=4)
        
    elif brand_name and cta:
        # Brand text (centered, y=870)
        try:
            if hasattr(font_reg, 'getbbox'):
                w_b = font_reg.getbbox(brand_name)[2]
            else:
                w_b = font_reg.getsize(brand_name)[0]
        except Exception:
            w_b = len(brand_name) * 26 * 0.6
        draw.text(((width - w_b) // 2, 870), brand_name, fill=(210, 210, 210, 255), font=font_reg)
        
        # CTA Button (centered, y=940)
        btn_w = 360
        btn_h = 75
        btn_x = (width - btn_w) // 2
        btn_y = 940
        try:
            # Rounded filled rectangle with white border
            draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], radius=15, fill=(139, 92, 246, 130), outline=(255, 255, 255, 255), width=3)
        except Exception:
            draw.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], fill=(139, 92, 246, 130), outline=(255, 255, 255, 255), width=3)
            
        try:
            if hasattr(font_bold, 'getbbox'):
                w_c = font_bold.getbbox(cta)[2]
            else:
                w_c = font_bold.getsize(cta)[0]
        except Exception:
            w_c = len(cta) * 44 * 0.6
        draw.text((btn_x + (btn_w - w_c) // 2, btn_y + (btn_h - 52) // 2), cta, fill=(255, 255, 255, 255), font=font_bold)
        
    img_array = np.array(image)
    rgb_array = img_array[:, :, :3]
    alpha_array = img_array[:, :, 3] / 255.0
    
    mask = ImageClip(alpha_array, is_mask=True).with_duration(duration)
    clip = ImageClip(rgb_array).with_mask(mask).with_duration(duration)
    return clip


def generate_product_promo_video(task_id, images_paths, brand_name, product_name, highlights, bg_music_path, output_path, progress_callback):
    """Generate a 15-second vertical (720x1280) product promotion video."""
    progress_callback(task_id, 10, "正在讀取並處理商品圖片...")
    
    if not images_paths:
        raise ValueError("必須提供至少一張商品圖片！")
        
    # Ensure at least 6 image paths are available
    working_imgs = list(images_paths)
    while len(working_imgs) < 6:
        working_imgs = working_imgs + working_imgs
        
    scene_dur = 2.5
    clips = []
    
    # Process 6 scenes (total 15 seconds)
    for i in range(6):
        img_path = working_imgs[i]
        img = process_promo_image(img_path)
        
        img_clip = ImageClip(np.array(img)).with_duration(scene_dur)
        # Apply smooth zoom effect (zoom from 100% to 110% over 2.5s)
        img_clip = img_clip.resized(lambda t: 1.0 + 0.04 * t)
        
        # Set scene text overlays
        if i == 0:
            overlay = create_promo_text_overlay(brand_name, product_name, None, None, duration=scene_dur)
        elif i == 1:
            overlay = create_promo_text_overlay(None, None, highlights[0] if len(highlights) > 0 else "", None, duration=scene_dur)
        elif i == 2:
            overlay = create_promo_text_overlay(None, None, highlights[1] if len(highlights) > 1 else "", None, duration=scene_dur)
        elif i == 3:
            overlay = create_promo_text_overlay(None, None, highlights[2] if len(highlights) > 2 else "", None, duration=scene_dur)
        elif i == 4:
            overlay = create_promo_text_overlay(None, None, "頂級工藝 卓越品質", None, duration=scene_dur)
        else: # i == 5
            overlay = create_promo_text_overlay(brand_name, None, None, "立即選購", duration=scene_dur)
            
        scene = CompositeVideoClip([img_clip, overlay]).with_duration(scene_dur)
        scene = scene.with_start(i * scene_dur)
        clips.append(scene)
        
    progress_callback(task_id, 35, "正在合成串聯軌道並剪輯音樂...")
    video = CompositeVideoClip(clips).with_duration(15.0)
    
    if bg_music_path and os.path.exists(bg_music_path):
        progress_callback(task_id, 50, "正在剪輯與混音背景音樂...")
        try:
            audio = AudioFileClip(bg_music_path)
            if audio.duration < 15.0:
                audio = audio.with_effects([AudioLoop(duration=15.0)])
            else:
                audio = audio.subclipped(0, 15.0)
            audio = audio.with_effects([AudioFadeOut(1.0)])
            video = video.with_audio(audio)
        except Exception as e:
            print(f"Error adding audio to promo: {e}")
            
    progress_callback(task_id, 65, "正在開始影片渲染編碼...")
    logger = CustomMoviePyLogger(task_id, progress_callback)
    
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=logger
    )
    
    video.close()
    for c in clips:
        c.close()
    progress_callback(task_id, 100, "影片生成完成！")


def generate_default_previews(templates_dir, assets_dir):
    """Automatically pre-generate preview videos for the templates using programmatically generated assets."""
    os.makedirs(templates_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)
    
    slideshow_preview = os.path.join(templates_dir, "slideshow_preview.mp4")
    meme_preview = os.path.join(templates_dir, "meme_preview.mp4")
    intro_preview = os.path.join(templates_dir, "intro_preview.mp4")
    promo_preview = os.path.join(templates_dir, "promo_preview.mp4")
    
    # 1. Write a dummy beep sound to assets for intro / slideshow background
    beep_path = os.path.join(assets_dir, "default_audio.mp3")
    if not os.path.exists(beep_path):
        # Generate simple sound file using moviepy synthesized tone
        def make_tone(t):
            return np.sin(2 * np.pi * 330 * t) + np.sin(2 * np.pi * 440 * t)
        
        tone = AudioClip(make_tone, duration=15, fps=44100)
        tone.write_audiofile(beep_path, fps=44100, logger=None)
        tone.close()
        
    # 2. Write dummy images to generate preview
    dummy_imgs = []
    colors = [(220, 50, 50), (50, 220, 50), (50, 50, 220)]
    for idx, col in enumerate(colors):
        path = os.path.join(assets_dir, f"temp_slide_{idx}.png")
        img = Image.new("RGB", (1280, 720), col)
        draw = ImageDraw.Draw(img)
        draw.text((640 - 50, 360 - 20), f"Sample Slide {idx+1}", fill=(255,255,255))
        img.save(path)
        dummy_imgs.append(path)
        
    dummy_logo = os.path.join(assets_dir, "default_logo.png")
    if not os.path.exists(dummy_logo):
        img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([50, 50, 250, 250], fill=(138, 43, 226, 255), outline=(255, 255, 255, 255), width=5)
        draw.text((120, 110), "A", fill=(255, 255, 255, 255), font_size=80)
        img.save(dummy_logo)
        
    # Generate Slideshow Preview
    if not os.path.exists(slideshow_preview):
        print("Generating slideshow preview video...")
        try:
            generate_slideshow_video(
                "init_slideshow", 
                dummy_imgs, 
                "時尚影集範本預覽", 
                beep_path, 
                slideshow_preview, 
                lambda *args: None
            )
        except Exception as e:
            print(f"Error generating slideshow preview: {e}")
            
    # Generate Meme Preview (needs a base video clip)
    base_video = os.path.join(assets_dir, "temp_base_video.mp4")
    if not os.path.exists(base_video):
        # Create a simple rotating color block video
        def make_frame(t):
            color = int(127 + 127 * np.sin(t * np.pi))
            img = Image.new("RGB", (1280, 720), (color, 100, 200 - color))
            draw = ImageDraw.Draw(img)
            draw.rectangle([540, 260, 740, 460], fill=(255, 255, 255))
            return np.array(img)
            
        from moviepy import VideoClip
        vc = VideoClip(make_frame, duration=5.0)
        vc.write_videofile(base_video, fps=24, codec="libx264", logger=None)
        vc.close()
        
    if not os.path.exists(meme_preview):
        print("Generating meme preview video...")
        try:
            generate_meme_video(
                "init_meme", 
                base_video, 
                "WHEN THE CODE COMPILES", 
                "ON THE FIRST TRY", 
                meme_preview, 
                lambda *args: None
            )
        except Exception as e:
            print(f"Error generating meme preview: {e}")
            
    # Generate Logo Intro Preview
    if not os.path.exists(intro_preview):
        print("Generating logo intro preview video...")
        try:
            generate_logo_intro_video(
                "init_intro", 
                dummy_logo, 
                "Antigravity Studio", 
                "Create without boundaries", 
                beep_path, 
                intro_preview, 
                lambda *args: None
            )
        except Exception as e:
            print(f"Error generating intro preview: {e}")
            
    # Generate Product Promo Preview
    if not os.path.exists(promo_preview):
        print("Generating product promo preview video...")
        try:
            promo_imgs = dummy_imgs * 2
            generate_product_promo_video(
                "init_promo", 
                promo_imgs, 
                "Aether Studio", 
                "北歐風極簡藍牙喇叭", 
                ["劇院級立體環繞音效", "24小時長效續航力", "極簡工藝 美學設計"], 
                beep_path, 
                promo_preview, 
                lambda *args: None
            )
        except Exception as e:
            print(f"Error generating promo preview: {e}")
            
    # Clean up temp slides/base video
    for p in dummy_imgs + [base_video]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
