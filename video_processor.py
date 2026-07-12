import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Import MoviePy 2.x classes directly from package
try:
    from moviepy import VideoFileClip, ImageClip, ColorClip, CompositeVideoClip, AudioFileClip, AudioClip, vfx, concatenate_videoclips
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
    concatenate_videoclips = None
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


def mix_video_audio(final_video, bg_music=None, bg_music_volume=0.7, voiceover=None, voiceover_volume=1.0):
    """
    Composites background music and voiceover audio track over the video's original audio (if any),
    supporting independent volume controls for both.
    """
    from moviepy.audio.AudioClip import CompositeAudioClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    
    audio_clips = []
    
    # 1. Capture original video audio if it exists
    if final_video.audio is not None:
        audio_clips.append(final_video.audio)
        
    # 2. Add Background Music
    if bg_music and os.path.exists(bg_music):
        try:
            bg_clip = AudioFileClip(bg_music)
            if bg_clip.duration < final_video.duration:
                from moviepy.audio.fx.AudioLoop import AudioLoop
                bg_clip = bg_clip.with_effects([AudioLoop(duration=final_video.duration)])
            else:
                bg_clip = bg_clip.subclipped(0, final_video.duration)
                
            from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
            bg_clip = bg_clip.with_effects([AudioFadeOut(1.5)])
            bg_clip = bg_clip.with_volume_scaled(float(bg_music_volume))
            audio_clips.append(bg_clip)
        except Exception as e:
            print(f"Error loading background music {bg_music}: {e}")
            
    # 3. Add Voiceover
    if voiceover and os.path.exists(voiceover):
        try:
            vo_clip = AudioFileClip(voiceover)
            if vo_clip.duration > final_video.duration:
                vo_clip = vo_clip.subclipped(0, final_video.duration)
            else:
                vo_clip = vo_clip.with_duration(vo_clip.duration)
                
            from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
            vo_clip = vo_clip.with_effects([AudioFadeOut(1.5)])
            vo_clip = vo_clip.with_volume_scaled(float(voiceover_volume))
            audio_clips.append(vo_clip)
        except Exception as e:
            print(f"Error loading voiceover {voiceover}: {e}")
            
    if audio_clips:
        composite_audio = CompositeAudioClip(audio_clips)
        composite_audio = composite_audio.with_duration(final_video.duration)
        final_video = final_video.with_audio(composite_audio)
        
    return final_video


def generate_slideshow_video(task_id, images_paths, title, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume, output_path, progress_callback):
    """Generate a slideshow from images with transitions, title overlay, and background music."""
    progress_callback(task_id, 10, "正在讀取並處理圖片...")
    
    if not images_paths:
        raise ValueError("沒有提供圖片素材！")
        
    img_dur = 3.0
    fade_dur = 1.0
    
    clips = []
    for i, img_path in enumerate(images_paths):
        # Read and scale image centered on canvas
        processed_img = process_slideshow_image(img_path)
        
        temp_img_path = img_path + "_resized.png"
        processed_img.save(temp_img_path)
        
        img_clip = ImageClip(temp_img_path).with_duration(img_dur + fade_dur)
        
        try: os.remove(temp_img_path)
        except Exception: pass
        
        # Apply smooth zoom-in effect
        clip = img_clip.resized(lambda t: 1.0 + (0.05 * t / (img_dur + fade_dur)))
        
        # Add crossfade transition (fade-in only, except first clip)
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
        
    # Audio Mixing
    progress_callback(task_id, 45, "正在進行混音處理...")
    video = mix_video_audio(video, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume)
            
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


def generate_meme_video(task_id, video_path, top_text, bottom_text, bg_music, bg_music_volume, voiceover, voiceover_volume, output_path, progress_callback):
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
        
    progress_callback(task_id, 60, "正在進行混音處理...")
    video = mix_video_audio(video, bg_music, bg_music_volume, voiceover, voiceover_volume)
        
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


def generate_logo_intro_video(task_id, logo_path, brand_name, tagline, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume, output_path, progress_callback):
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
    
    progress_callback(task_id, 50, "正在進行混音處理...")
    video = mix_video_audio(video, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume)
            
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


def generate_product_promo_video(task_id, images_paths, brand_name, product_name, highlights, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume, output_path, progress_callback):
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
    
    progress_callback(task_id, 50, "正在進行混音處理...")
    video = mix_video_audio(video, bg_music_path, bg_music_volume, voiceover_path, voiceover_volume)
            
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


def create_custom_text_overlay(text_items, width, height, duration):
    """Creates a transparent ImageClip overlay with multiple text items positioned custom-style using Pillow."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    font_cache = {}
    
    def get_font(size):
        if size in font_cache:
            return font_cache[size]
        font_bold = None
        font_names = []
        if sys.platform.startswith("win"):
            font_names = ["msjhbd.ttc", "msjh.ttc", "arialbd.ttf", "arial.ttf", "simsun.ttc"]
        elif sys.platform.startswith("darwin"):
            font_names = ["/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial.ttf"]
        else:
            font_names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            
        for fn in font_names:
            try:
                font_bold = ImageFont.truetype(fn, size)
                break
            except Exception:
                continue
        if not font_bold:
            font_bold = ImageFont.load_default()
        font_cache[size] = font_bold
        return font_bold

    for item in text_items:
        content = item.get("content", "")
        if not content:
            continue
        
        size = int(item.get("font_size", 40))
        color_hex = item.get("color", "#ffffff")
        position = item.get("position", "center")
        
        # Parse color hex to RGBA
        try:
            h = color_hex.lstrip('#')
            fill_color = tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        except Exception:
            fill_color = (255, 255, 255, 255)
            
        font = get_font(size)
        
        # Calculate size
        try:
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(content)
                w_t = bbox[2] - bbox[0]
                h_t = bbox[3] - bbox[1]
            else:
                w_t, h_t = font.getsize(content)
        except Exception:
            w_t = len(content) * size * 0.6
            h_t = size
            
        # Parse position (9-grid positions)
        safe_margin_x = int(width * 0.05)
        safe_margin_y = int(height * 0.05)
        
        if position == "top_left":
            x = safe_margin_x
            y = safe_margin_y
        elif position == "top_center" or position == "top":
            x = (width - w_t) // 2
            y = safe_margin_y
        elif position == "top_right":
            x = width - w_t - safe_margin_x
            y = safe_margin_y
        elif position == "center_left":
            x = safe_margin_x
            y = (height - h_t) // 2
        elif position == "center":
            x = (width - w_t) // 2
            y = (height - h_t) // 2
        elif position == "center_right":
            x = width - w_t - safe_margin_x
            y = (height - h_t) // 2
        elif position == "bottom_left":
            x = safe_margin_x
            y = height - h_t - safe_margin_y
        elif position == "bottom_center" or position == "bottom":
            x = (width - w_t) // 2
            y = height - h_t - safe_margin_y
        elif position == "bottom_right":
            x = width - w_t - safe_margin_x
            y = height - h_t - safe_margin_y
        elif "," in position:
            try:
                px, py = position.split(",")
                x = int(float(px) * width) if float(px) < 1 else int(px)
                y = int(float(py) * height) if float(py) < 1 else int(py)
            except Exception:
                x = (width - w_t) // 2
                y = (height - h_t) // 2
        else:
            x = (width - w_t) // 2
            y = (height - h_t) // 2
            
        # Draw soft shadow for readability
        draw.text((x + 2, y + 2), content, fill=(0, 0, 0, 180), font=font)
        draw.text((x, y), content, fill=fill_color, font=font)
        
    overlay = ImageClip(np.array(image))
    overlay = overlay.with_duration(duration)
    return overlay


def generate_custom_template_video(task_id, custom_tpl, file_paths, bg_music, bg_music_volume, voiceover, voiceover_volume, output_path, progress_callback):
    """
    Renders a custom template video containing multiple user-defined scenes,
    applying zoom animations, text timelines, and background music.
    """
    progress_callback(task_id, 10, "正在加載自訂影片範本設定...")
    
    aspect_ratio = custom_tpl.get("aspect_ratio", "9:16")
    if aspect_ratio == "16:9":
        width, height = 1280, 720
    else:
        width, height = 720, 1280
        
    scenes = custom_tpl.get("scenes", [])
    clips = []
    
    total_scenes = len(scenes)
    for idx, scene in enumerate(scenes):
        progress_callback(task_id, int(10 + (idx / total_scenes) * 50), f"正在合成場景 {idx+1}/{total_scenes}...")
        
        duration = float(scene.get("duration", 3.0))
        visual_type = scene.get("visual_type", "image_zoom")
        
        # Auto duration matching for user videos
        if visual_type == "user_video":
            field_name = scene.get("asset_field", f"scene_{idx}_file")
            video_path = file_paths.get(field_name)
            if video_path and os.path.exists(video_path):
                if duration <= 0:
                    try:
                        temp_c = VideoFileClip(video_path)
                        duration = temp_c.duration
                        temp_c.close()
                    except Exception:
                        duration = 3.0
            else:
                if duration <= 0:
                    duration = 3.0
        else:
            if duration <= 0:
                duration = 3.0
        
        base_clip = None
        
        if visual_type == "image_zoom":
            field_name = scene.get("asset_field", f"scene_{idx}_file")
            image_path = file_paths.get(field_name)
            
            if not image_path or not os.path.exists(image_path):
                from moviepy.video.VideoClip import ColorClip
                base_clip = ColorClip(size=(width, height), color=(60, 60, 60), duration=duration)
            else:
                cropped_img = process_promo_image(image_path, width, height)
                
                temp_cropped_path = image_path + "_cropped.png"
                cropped_img.save(temp_cropped_path)
                
                img_clip = ImageClip(temp_cropped_path).with_duration(duration)
                
                try: os.remove(temp_cropped_path)
                except Exception: pass
                
                zoom_dir = scene.get("zoom_direction", "in")
                if zoom_dir == "in":
                    resize_func = lambda t: 1.0 + (0.08 * (t / duration))
                else:
                    resize_func = lambda t: 1.08 - (0.08 * (t / duration))
                    
                base_clip = img_clip.resized(resize_func)
                
        elif visual_type == "user_video":
            field_name = scene.get("asset_field", f"scene_{idx}_file")
            video_path = file_paths.get(field_name)
            
            if not video_path or not os.path.exists(video_path):
                from moviepy.video.VideoClip import ColorClip
                base_clip = ColorClip(size=(width, height), color=(60, 60, 60), duration=duration)
            else:
                user_clip = VideoFileClip(video_path)
                
                clip_dur = user_clip.duration
                if clip_dur < duration:
                    base_clip = user_clip.subclipped(0, clip_dur).with_duration(duration)
                else:
                    base_clip = user_clip.subclipped(0, duration)
                    
                clip_w, clip_h = base_clip.size
                scale = max(width / clip_w, height / clip_h)
                scaled_w, scaled_h = int(clip_w * scale), int(clip_h * scale)
                
                base_clip = base_clip.resized((scaled_w, scaled_h))
                crop_x = (scaled_w - width) // 2
                crop_y = (scaled_h - height) // 2
                
                from moviepy.video.fx.Crop import Crop
                base_clip = base_clip.with_effects([Crop(x1=crop_x, y1=crop_y, width=width, height=height)])
                
                # Apply Audio settings (mute or volume control)
                audio_option = scene.get("audio_option", "keep")
                if base_clip.audio is not None:
                    if audio_option == "mute":
                        base_clip = base_clip.without_audio()
                    elif audio_option == "volume":
                        vol_scale = float(scene.get("audio_volume", 1.0))
                        base_clip = base_clip.with_audio(base_clip.audio.with_volume_scaled(vol_scale))
                
        elif visual_type == "solid_color":
            color_hex = scene.get("color", "#000000")
            try:
                h = color_hex.lstrip('#')
                col_rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                col_rgb = (0, 0, 0)
                
            from moviepy.video.VideoClip import ColorClip
            base_clip = ColorClip(size=(width, height), color=col_rgb, duration=duration)
            
        else:
            from moviepy.video.VideoClip import ColorClip
            base_clip = ColorClip(size=(width, height), color=(0, 0, 0), duration=duration)
            
        # Check if text overlay is enabled for this scene
        enable_text = scene.get("enable_text", True)
        text_items = scene.get("texts", []) if enable_text else []
        scene_composited_clips = [base_clip]
        
        for text in text_items:
            content = text.get("content", "")
            if not content:
                continue
            start_t = max(0.0, float(text.get("start_time", 0.0)))
            end_t = min(duration, float(text.get("end_time", duration)))
            if start_t >= end_t:
                continue
                
            text_duration = end_t - start_t
            text_clip = create_custom_text_overlay([text], width, height, text_duration)
            text_clip = text_clip.with_start(start_t)
            
            scene_composited_clips.append(text_clip)
            
        scene_final_clip = CompositeVideoClip(scene_composited_clips, size=(width, height)).with_duration(duration)
        clips.append(scene_final_clip)
        
    progress_callback(task_id, 70, "正在連接所有自訂場景並套用轉場效果...")
    transition_effect = custom_tpl.get("transition_effect", "none")
    
    if transition_effect == "crossfade" and len(clips) > 1:
        overlap = 0.5
        composited_clips = []
        current_start = 0.0
        
        for idx, clip in enumerate(clips):
            if idx == 0:
                clip = clip.with_start(0.0)
                composited_clips.append(clip)
                current_start += clip.duration
            else:
                clip_start = current_start - overlap
                clip = clip.with_start(clip_start)
                clip = clip.with_effects([vfx.FadeIn(overlap)])
                composited_clips.append(clip)
                current_start = clip_start + clip.duration
                
        total_duration = current_start
        final_video = CompositeVideoClip(composited_clips, size=(width, height)).with_duration(total_duration)
    else:
        if transition_effect == "fade":
            fade_clips = []
            for clip in clips:
                faded = clip.with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
                fade_clips.append(faded)
            final_video = concatenate_videoclips(fade_clips, method="compose")
        else:
            final_video = concatenate_videoclips(clips, method="compose")
    
    progress_callback(task_id, 80, "正在進行混音處理...")
    final_video = mix_video_audio(final_video, bg_music, bg_music_volume, voiceover, voiceover_volume)
            
    progress_callback(task_id, 85, "正在啟動自訂影片編碼渲染...")
    logger = CustomMoviePyLogger(task_id, progress_callback)
    
    final_video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=logger
    )
    
    final_video.close()
    for c in clips:
        c.close()
        
    progress_callback(task_id, 100, "影片生成完成！")


def process_media_tool_temp(input_file_path: str, action: str, output_path: str):
    """
    Applies media tools (like muting video or extracting audio) to a file,
    saving the output directly to a temporary output path.
    """
    if not os.path.exists(input_file_path):
        raise ValueError(f"找不到所選的來源檔案: {input_file_path}")
        
    if action == "mute":
        clip = VideoFileClip(input_file_path)
        muted_clip = clip.without_audio()
        
        muted_clip.write_videofile(
            output_path,
            fps=clip.fps or 24,
            codec="libx264",
            logger=None
        )
        clip.close()
        muted_clip.close()
        
    elif action == "extract":
        clip = VideoFileClip(input_file_path)
        if not clip.audio:
            clip.close()
            raise ValueError("此影片不包含任何音軌。")
            
        audio_clip = clip.audio
        audio_clip.write_audiofile(
            output_path,
            fps=44100,
            logger=None
        )
        clip.close()
        
    else:
        raise ValueError(f"未知的處理動作: {action}")


def process_media_tool(input_file_path: str, action: str, library_dir: str, load_db_func, save_db_func) -> str:
    """
    Applies media tools (like muting video or extracting audio) to a file in the media library,
    saving the output to the correct subfolder (movies/music) and registering it in the metadata DB.
    """
    if not os.path.exists(input_file_path):
        raise ValueError(f"找不到所選的來源檔案: {input_file_path}")
        
    filename = os.path.basename(input_file_path)
    db = load_db_func()
    asset_record = db.get("assets", {}).get(filename)
    if not asset_record:
        asset_record = {"name": filename, "type": "video"}
        
    original_name = asset_record.get("name", filename)
    name_without_ext, ext = os.path.splitext(filename)
    orig_name_without_ext, orig_ext = os.path.splitext(original_name)
    
    import uuid
    from datetime import datetime
    
    if action == "mute":
        output_filename = f"muted_{uuid.uuid4().hex[:6]}_{filename}"
        output_dir = os.path.join(library_dir, "movies")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_filename)
        
        clip = VideoFileClip(input_file_path)
        muted_clip = clip.without_audio()
        
        muted_clip.write_videofile(
            output_path,
            fps=clip.fps or 24,
            codec="libx264",
            logger=None
        )
        clip.close()
        muted_clip.close()
        
        db["assets"][output_filename] = {
            "filename": output_filename,
            "name": f"[靜音] {original_name}",
            "memo": f"自影片「{original_name}」去除聲音後的影片。",
            "type": "video",
            "url": f"/library/movies/{output_filename}",
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_db_func(db)
        return output_filename
        
    elif action == "extract":
        output_filename = f"extracted_{uuid.uuid4().hex[:6]}_{name_without_ext}.mp3"
        output_dir = os.path.join(library_dir, "music")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_filename)
        
        clip = VideoFileClip(input_file_path)
        if not clip.audio:
            clip.close()
            raise ValueError("此影片不包含任何音軌。")
            
        audio_clip = clip.audio
        audio_clip.write_audiofile(
            output_path,
            fps=44100,
            logger=None
        )
        clip.close()
        
        db["assets"][output_filename] = {
            "filename": output_filename,
            "name": f"[音訊] {orig_name_without_ext}.mp3",
            "memo": f"自影片「{original_name}」提取出的 MP3 音訊檔。",
            "type": "audio",
            "url": f"/library/music/{output_filename}",
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_db_func(db)
        return output_filename
        
    else:
        raise ValueError(f"未知的處理動作: {action}")


def delete_default_previews(templates_dir, library_photos_dir, library_music_dir):
    """Deletes the old default ugly preview videos from the system, while ensuring system assets exist."""
    # Delete MP4s
    for f in ["slideshow_preview.mp4", "meme_preview.mp4", "intro_preview.mp4", "promo_preview.mp4"]:
        path = os.path.join(templates_dir, f)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    # Ensure system assets exist
    beep_path = os.path.join(library_music_dir, "default_audio.mp3")
    if not os.path.exists(beep_path):
        try:
            def make_tone(t):
                return np.sin(2 * np.pi * 330 * t) + np.sin(2 * np.pi * 440 * t)
            tone = AudioClip(make_tone, duration=15, fps=44100)
            tone.write_audiofile(beep_path, fps=44100, logger=None)
            tone.close()
        except Exception as e:
            print(f"Error generating default audio: {e}")

    dummy_logo = os.path.join(library_photos_dir, "default_logo.png")
    if not os.path.exists(dummy_logo):
        try:
            img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([50, 50, 250, 250], fill=(138, 43, 226, 255), outline=(255, 255, 255, 255), width=5)
            draw.text((120, 110), "V", fill=(255, 255, 255, 255), font_size=80)
            img.save(dummy_logo)
        except Exception as e:
            print(f"Error generating default logo: {e}")


def generate_blend_effect_video(task_id, img1_path, img2_path, duration, fade_duration, output_path, progress_callback):
    progress_callback(task_id, 10, "正在載入圖片素材...")
    
    half_dur = duration / 2.0
    half_fade = fade_duration / 2.0
    
    c1_dur = half_dur + half_fade
    c2_dur = half_dur + half_fade
    c2_start = half_dur - half_fade
    
    clip1 = ImageClip(img1_path).with_duration(c1_dur).resized((1280, 720))
    clip2 = ImageClip(img2_path).with_duration(c2_dur).resized((1280, 720))
    
    clip2 = clip2.with_effects([vfx.FadeIn(fade_duration)]).with_start(c2_start)
    
    progress_callback(task_id, 30, "正在合成漸變特效影片...")
    
    final_clip = CompositeVideoClip([clip1, clip2], size=(1280, 720))
    
    final_clip.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        logger=None
    )
    
    final_clip.close()
    clip1.close()
    clip2.close()
    progress_callback(task_id, 100, "特效影片生成完成！")


def generate_filter_effect_video(task_id, img_path, filter_type, duration, output_path, progress_callback):
    progress_callback(task_id, 10, "正在載入圖片與套用濾鏡...")
    
    if filter_type == "mirror_x":
        img = Image.open(img_path)
        img_mirrored = img.transpose(Image.FLIP_LEFT_RIGHT)
        clip = ImageClip(np.array(img_mirrored)).with_duration(duration).resized((1280, 720))
    elif filter_type == "sepia":
        img = Image.open(img_path).convert("RGB")
        arr = np.array(img)
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        tr = 0.393 * r + 0.769 * g + 0.189 * b
        tg = 0.349 * r + 0.686 * g + 0.168 * b
        tb = 0.272 * r + 0.534 * g + 0.131 * b
        sepia_arr = np.stack([tr, tg, tb], axis=-1)
        sepia_arr = np.clip(sepia_arr, 0, 255).astype(np.uint8)
        clip = ImageClip(sepia_arr).with_duration(duration).resized((1280, 720))
    elif filter_type == "grayscale":
        img = Image.open(img_path).convert("L").convert("RGB")
        clip = ImageClip(np.array(img)).with_duration(duration).resized((1280, 720))
    else:
        clip = ImageClip(img_path).with_duration(duration).resized((1280, 720))
        
    if filter_type == "ken_burns":
        clip = clip.resized(lambda t: 1.0 + 0.15 * (t / duration))
    elif filter_type == "fade":
        clip = clip.with_effects([vfx.FadeIn(0.8), vfx.FadeOut(0.8)])
        
    progress_callback(task_id, 40, "正在生成濾鏡特效影片...")
    
    final_clip = CompositeVideoClip([clip], size=(1280, 720)) if filter_type == "ken_burns" else clip
    
    final_clip.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        logger=None
    )
    
    final_clip.close()
    if filter_type == "ken_burns":
        clip.close()
        
    progress_callback(task_id, 100, "特效影片生成完成！")


def generate_multi_transition_video(task_id, img_paths, transition_type, slide_duration, transition_duration, output_path, progress_callback):
    progress_callback(task_id, 10, f"正在載入 {len(img_paths)} 張圖片素材...")
    
    clips = []
    step = slide_duration - transition_duration
    
    for i, path in enumerate(img_paths):
        c = ImageClip(path).with_duration(slide_duration).resized((1280, 720))
        
        if i > 0:
            c = c.with_effects([vfx.FadeIn(transition_duration)])
            c = c.with_start(i * step)
        else:
            c = c.with_start(0)
            
        clips.append(c)
        
    progress_callback(task_id, 40, "正在合成多圖轉場影片...")
    
    final_clip = CompositeVideoClip(clips, size=(1280, 720))
    
    final_clip.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        logger=None
    )
    
    final_clip.close()
    for c in clips:
        c.close()
        
    progress_callback(task_id, 100, "轉場影片生成完成！")


def load_media_clip(path, duration):
    ext = path.split('.')[-1].lower() if '.' in path else ''
    if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
        c = VideoFileClip(path)
        if c.duration and c.duration < duration:
            times = int(np.ceil(duration / c.duration))
            c = concatenate_videoclips([c] * times).subclipped(0, duration)
        else:
            c = c.subclipped(0, duration)
        return c
    else:
        return ImageClip(path).with_duration(duration)


def generate_alpha_blend_video(task_id, media1_path, media2_path, opacity, duration, output_path, progress_callback):
    progress_callback(task_id, 10, "正在載入並解析底層與頂層素材...")
    
    clip1 = load_media_clip(media1_path, duration).resized((1280, 720))
    clip2 = load_media_clip(media2_path, duration).resized((1280, 720))
    
    progress_callback(task_id, 30, f"正在套用 {opacity} 半透明度疊加...")
    clip2 = clip2.with_opacity(opacity)
    
    progress_callback(task_id, 50, "正在合成半透明疊加影片...")
    final_clip = CompositeVideoClip([clip1, clip2], size=(1280, 720)).with_duration(duration)
    
    final_clip.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        logger=None
    )
    
    final_clip.close()
    clip1.close()
    clip2.close()
    progress_callback(task_id, 100, "半透明疊加影片合成完成！")


def generate_grid_layout_video(task_id, media_paths, cols, rows, duration, gap, output_path, progress_callback):
    progress_callback(task_id, 10, f"正在載入 {len(media_paths)} 個宮格素材...")
    
    cell_w = int((1280 - (cols + 1) * gap) / cols)
    cell_h = int((720 - (rows + 1) * gap) / rows)
    
    clips = []
    bg_clip = ColorClip(size=(1280, 720), color=(0, 0, 0)).with_duration(duration)
    clips.append(bg_clip)
    
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if idx >= len(media_paths):
                break
                
            path = media_paths[idx]
            progress_callback(task_id, 20 + int(idx * 20 / len(media_paths)), f"正在載入第 {idx+1} 個宮格素材...")
            
            cell_clip = load_media_clip(path, duration).resized((cell_w, cell_h))
            
            x = gap + c * (cell_w + gap)
            y = gap + r * (cell_h + gap)
            
            cell_clip = cell_clip.with_position((x, y))
            clips.append(cell_clip)
            
    progress_callback(task_id, 50, "正在合成宮格排版影片...")
    
    final_clip = CompositeVideoClip(clips, size=(1280, 720)).with_duration(duration)
    
    final_clip.write_videofile(
        output_path, 
        fps=24, 
        codec="libx264", 
        audio=False, 
        logger=None
    )
    
    final_clip.close()
    for clip in clips:
        clip.close()
        
    progress_callback(task_id, 100, "宮格影片合成完成！")
