import os
import uuid
import shutil
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks, Form, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import video_processor

app = FastAPI(title="MoviePy Video Generator")

# CORS middleware for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import json
from datetime import datetime

# Directories
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "outputs")
STATIC_DIR = os.path.join(WORKSPACE_DIR, "static")
TEMPLATES_DIR = os.path.join(STATIC_DIR, "templates")
LIBRARY_DIR = os.path.join(STATIC_DIR, "library")
LIBRARY_MOVIES_DIR = os.path.join(LIBRARY_DIR, "movies")
LIBRARY_PHOTOS_DIR = os.path.join(LIBRARY_DIR, "photos")
LIBRARY_MUSIC_DIR = os.path.join(LIBRARY_DIR, "music")

for directory in [OUTPUT_DIR, STATIC_DIR, TEMPLATES_DIR, LIBRARY_DIR, LIBRARY_MOVIES_DIR, LIBRARY_PHOTOS_DIR, LIBRARY_MUSIC_DIR]:
    os.makedirs(directory, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/library", StaticFiles(directory=LIBRARY_DIR), name="library")

# Global task status dictionary
tasks_status: Dict[str, Dict[str, Any]] = {}

DB_PATH = os.path.join(WORKSPACE_DIR, "metadata.json")

def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return {"assets": {}, "videos": {}}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"assets": {}, "videos": {}}
        
def save_db(db: Dict[str, Any]):
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving metadata DB: {e}")

def get_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".mp3", ".wav", ".aac", ".ogg", ".m4a"]:
        return "audio"
    elif ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        return "video"
    else:
        return "image"

def get_library_file_path(filename: str) -> str:
    db = load_db()
    info = db.get("assets", {}).get(filename, {})
    file_type = info.get("type", get_file_type(filename))
    if file_type == "audio":
        return os.path.join(LIBRARY_MUSIC_DIR, filename)
    elif file_type == "video":
        return os.path.join(LIBRARY_MOVIES_DIR, filename)
    else:
        return os.path.join(LIBRARY_PHOTOS_DIR, filename)

def migrate_existing_library_files(first_run: bool = True):
    db = load_db()
    db_changed = False
    
    # 1. Migrate existing files inside LIBRARY_DIR root to subfolders
    for filename in list(db.get("assets", {}).keys()):
        asset_info = db["assets"][filename]
        file_type = asset_info.get("type", get_file_type(filename))
        
        old_path = os.path.join(LIBRARY_DIR, filename)
        
        if file_type == "image":
            new_path = os.path.join(LIBRARY_PHOTOS_DIR, filename)
            url_prefix = "/library/photos"
        elif file_type == "video":
            new_path = os.path.join(LIBRARY_MOVIES_DIR, filename)
            url_prefix = "/library/movies"
        else: # audio
            new_path = os.path.join(LIBRARY_MUSIC_DIR, filename)
            url_prefix = "/library/music"
            
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                shutil.move(old_path, new_path)
                print(f"Migrated library file: {filename} -> {new_path}")
            except Exception as e:
                print(f"Failed to move file {filename}: {e}")
                
        old_url = f"/library/{filename}"
        new_url = f"{url_prefix}/{filename}"
        if asset_info.get("url") == old_url:
            asset_info["url"] = new_url
            db_changed = True
            
    if first_run:
        # 2. Scan LIBRARY_MUSIC_DIR and register unregistered files in DB
        if os.path.exists(LIBRARY_MUSIC_DIR):
            for f in os.listdir(LIBRARY_MUSIC_DIR):
                if f.endswith(".mp3") or f.endswith(".wav"):
                    if f not in db.get("assets", {}):
                        name_without_ext = os.path.splitext(f)[0]
                        label = name_without_ext.replace("_", " ").title()
                        custom_labels = {
                            "upbeat_electro": "輕快動感電音",
                            "chill_vibes": "放鬆律動音樂",
                            "acoustic_peace": "溫馨和平吉他",
                            "ambient": "靈動氛圍音樂",
                            "tech": "科技感電子樂",
                            "cinematic": "磅礡電影音效",
                            "default_audio": "預設簡短提示音"
                        }
                        display_label = custom_labels.get(name_without_ext, label)
                        
                        db["assets"][f] = {
                            "filename": f,
                            "name": display_label,
                            "memo": "系統內建配樂素材",
                            "type": "audio",
                            "url": f"/library/music/{f}",
                            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        db_changed = True
                        print(f"Registered track in DB: {f}")
                        
        # 3. Register default logo in DB if it exists
        default_logo_filename = "default_logo.png"
        if os.path.exists(os.path.join(LIBRARY_PHOTOS_DIR, default_logo_filename)):
            if default_logo_filename not in db.get("assets", {}):
                db["assets"][default_logo_filename] = {
                    "filename": default_logo_filename,
                    "name": "系統預設 Logo 圖片",
                    "memo": "系統預設示範標誌圖片",
                    "type": "image",
                    "url": f"/library/photos/{default_logo_filename}",
                    "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                db_changed = True
                print("Registered default logo in DB.")
            
    if db_changed:
        save_db(db)

def update_task_progress(task_id: str, progress: int, message: str, status: str = "processing"):
    if task_id in tasks_status:
        tasks_status[task_id]["progress"] = progress
        tasks_status[task_id]["message"] = message
        tasks_status[task_id]["status"] = status


def download_audio_asset(url: str, dest_path: str):
    """Downloads a royalty-free audio file from the web, with bot-blocking user agent headers."""
    import urllib.request
    if os.path.exists(dest_path):
        return
    try:
        print(f"Downloading royalty-free audio from {url} to {dest_path}...")
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            with open(dest_path, "wb") as f:
                f.write(response.read())
        print(f"Downloaded {dest_path} successfully!")
    except Exception as e:
        print(f"Failed to download {url}: {e}")


# Startup events
@app.on_event("startup")
async def startup_event():
    db = load_db()
    first_run = not db.get("system_initialized", False)
    
    # Pre-generate preview videos programmatically on start
    print("Initializing system assets and default preview videos...")
    
    # 1. Asynchronously download royalty-free background music tracks to LIBRARY_MUSIC_DIR
    if first_run:
        urls = {
            "upbeat_electro.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            "chill_vibes.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
            "acoustic_peace.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
        }
        
        loop = asyncio.get_event_loop()
        for filename, url in urls.items():
            dest = os.path.join(LIBRARY_MUSIC_DIR, filename)
            if not os.path.exists(dest):
                loop.run_in_executor(None, download_audio_asset, url, dest)
            
    # 2. Generate ambient/tech/cinematic synth files for user selections inside LIBRARY_MUSIC_DIR
    if first_run:
        music_tracks = {
            "ambient.mp3": lambda t: np.sin(2 * np.pi * 220 * t) * 0.4 + np.sin(2 * np.pi * 275 * t) * 0.3,
            "tech.mp3": lambda t: np.sin(2 * np.pi * 440 * (t % 0.25 < 0.1) * t) * 0.3 + np.sin(2 * np.pi * 880 * (t % 0.25 < 0.05) * t) * 0.2,
            "cinematic.mp3": lambda t: np.sin(2 * np.pi * 110 * t) * 0.5 * (1 - np.exp(-t)) + np.sin(2 * np.pi * 165 * t) * 0.4
        }
        
        import numpy as np
        from moviepy.audio.AudioClip import AudioClip
        
        for filename, wave_func in music_tracks.items():
            path = os.path.join(LIBRARY_MUSIC_DIR, filename)
            if not os.path.exists(path):
                try:
                    print(f"Generating audio asset: {filename}...")
                    tone = AudioClip(wave_func, duration=30.0, fps=44100)
                    tone.write_audiofile(path, fps=44100, logger=None)
                    tone.close()
                except Exception as e:
                    print(f"Failed to generate synth {filename}: {e}")
                
    # 3. Initialize templates preview videos
    try:
        video_processor.generate_default_previews(TEMPLATES_DIR, LIBRARY_PHOTOS_DIR, LIBRARY_MUSIC_DIR)
    except Exception as e:
        print(f"Error generating preview templates: {e}")

    # 4. Run library directory migration, file classification, and database registration
    print("Running library migration and database registration...")
    try:
        migrate_existing_library_files(first_run=first_run)
    except Exception as e:
        print(f"Error during library database synchronization: {e}")

    # Mark system as initialized
    if first_run:
        db = load_db()
        db["system_initialized"] = True
        save_db(db)

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/api/templates")
async def get_templates():
    db = load_db()
    library_audios = []
    
    # Sort options to put recommended ones first, then others
    def sort_key(item):
        val = item.get("filename", "")
        if "upbeat" in val or "chill" in val or "acoustic" in val:
            return (0, val)
        elif "default_audio" in val:
            return (2, val)
        else:
            return (1, val)
            
    # Filter for audio types and sort them
    audio_items = [item for item in db.get("assets", {}).values() if item.get("type") == "audio"]
    audio_items.sort(key=sort_key)
    
    for info in audio_items:
        library_audios.append({
            "value": f"library:{info.get('filename')}",
            "label": f"🎵 {info.get('name')}"
        })
        
    # Combine library options and the custom upload option
    music_options = library_audios + [{"value": "custom", "label": "自行上傳音訊檔案 (.mp3/.wav)"}]
    sound_options = library_audios + [{"value": "custom", "label": "自行上傳音效檔案 (.mp3/.wav)"}]
    
    templates = [
        {
            "id": "slideshow",
            "name": "時尚相簿投影片 (Slideshow)",
            "description": "將多張精美照片以交叉淡入淡出（Crossfade）轉場流暢銜接，並在開頭疊加動態標題字幕，搭配選定之背景音樂，完美演繹故事細節。",
            "preview_url": "/static/templates/slideshow_preview.mp4",
            "fields": [
                {"name": "title", "label": "相簿標題文字", "type": "text", "placeholder": "例如：我的夏日度假回憶錄", "required": True},
                {"name": "music", "label": "選擇背景音樂", "type": "select", "options": music_options, "required": True},
                {"name": "images", "label": "上傳相片 (3-5 張)", "type": "file", "multiple": True, "accept": "image/*", "required": True},
                {"name": "custom_audio", "label": "上傳自訂音樂檔案", "type": "file", "multiple": False, "accept": "audio/*", "required": False, "conditional": "music=custom"}
            ]
        },
        {
            "id": "meme",
            "name": "迷因短片產生器 (Video Meme)",
            "description": "經典迷因文字排版。將影片上傳後，在頂部與底部加上醒目的黑邊白字多行字幕，並完整保留影片原音，製作專屬梗圖影片。",
            "preview_url": "/static/templates/meme_preview.mp4",
            "fields": [
                {"name": "top_text", "label": "頂部文字 (Top Caption)", "type": "text", "placeholder": "例如：當我的程式碼一次就跑過", "required": False},
                {"name": "bottom_text", "label": "底部文字 (Bottom Caption)", "type": "text", "placeholder": "例如：而且沒有任何 Warning", "required": False},
                {"name": "video", "label": "上傳影片短片 (MP4, 最多截取前 15 秒)", "type": "file", "multiple": False, "accept": "video/*", "required": True}
            ]
        },
        {
            "id": "intro",
            "name": "品牌 Logo 片頭 (Logo Intro)",
            "description": "5 秒極簡暗夜科技感片頭。您的品牌 Logo 會以平滑縮放與淡入形式展現，下方隨即浮現主要品牌名稱與副標標語，伴隨掃頻震撼音效。",
            "preview_url": "/static/templates/intro_preview.mp4",
            "fields": [
                {"name": "brand_name", "label": "品牌/團隊名稱", "type": "text", "placeholder": "例如：極致影像工作室", "required": True},
                {"name": "tagline", "label": "宣傳副標/標語", "type": "text", "placeholder": "例如：探索無限的創意可能", "required": False},
                {"name": "logo", "label": "上傳 Logo 圖片 (建議透明背景 PNG)", "type": "file", "multiple": False, "accept": "image/*", "required": True},
                {"name": "sound", "label": "選擇片頭音效", "type": "select", "options": sound_options, "required": True},
                {"name": "custom_audio", "label": "上傳自訂音效檔案", "type": "file", "multiple": False, "accept": "audio/*", "required": False, "conditional": "sound=custom"}
            ]
        },
        {
            "id": "product_promo",
            "name": "高質感商品宣傳短片 (Product Promo)",
            "description": "15 秒直式高節奏商品推廣短片。套用滿版裁剪與微幅縮放動畫，搭配品牌、商品名及三大賣點文字，適合發佈於 TikTok/Instagram Reels/Shorts 進行商品宣傳。",
            "preview_url": "/static/templates/promo_preview.mp4",
            "fields": [
                {"name": "brand_name", "label": "品牌/商店名稱", "type": "text", "placeholder": "例如：極致創意生活館", "required": True},
                {"name": "product_name", "label": "商品名稱", "type": "text", "placeholder": "例如：北歐風極簡雙層玻璃杯", "required": True},
                {"name": "highlight1", "label": "特色/亮點 1", "type": "text", "placeholder": "例如：耐高溫雙層防燙設計", "required": True},
                {"name": "highlight2", "label": "特色/亮點 2", "type": "text", "placeholder": "例如：高透光食品級矽硼玻璃", "required": True},
                {"name": "highlight3", "label": "特色/亮點 3", "type": "text", "placeholder": "例如：圓潤杯口 極致手感", "required": True},
                {"name": "images", "label": "上傳商品圖片 (3-6 張)", "type": "file", "multiple": True, "accept": "image/*", "required": True},
                {"name": "music", "label": "選擇背景音樂", "type": "select", "options": music_options, "required": True},
                {"name": "custom_audio", "label": "上傳自訂音樂檔案", "type": "file", "multiple": False, "accept": "audio/*", "required": False, "conditional": "music=custom"}
            ]
        }
    ]
    
    # Load custom templates from database dynamically
    db = load_db()
    custom_templates = db.get("custom_templates", {})
    for t_id, ct in custom_templates.items():
        fields = []
        for idx, scene in enumerate(ct.get("scenes", [])):
            visual_type = scene.get("visual_type", "image_zoom")
            field_name = scene.get("asset_field", f"scene_{idx}_file")
            
            if visual_type == "image_zoom":
                label = f"場景 {idx+1} 圖片素材 (圖片)"
                accept = "image/*"
                has_file = True
            elif visual_type == "user_video":
                label = f"場景 {idx+1} 影片素材 (短片)"
                accept = "video/*"
                has_file = True
            else:
                has_file = False
                
            if has_file:
                fields.append({
                    "name": field_name,
                    "label": label,
                    "type": "file",
                    "multiple": False,
                    "accept": accept,
                    "required": True
                })
                
            if scene.get("enable_text", True):
                for t_idx, text in enumerate(scene.get("texts", [])):
                    fields.append({
                        "name": f"scene_{idx}_text_{t_idx}",
                        "label": f"場景 {idx+1} 文字 #{t_idx+1}",
                        "type": "text",
                        "placeholder": "輸入以修改文字 (留空則隱藏)",
                        "default": text.get("content", ""),
                        "required": False
                    })
            
        # Add background music options
        fields.append({
            "name": "music",
            "label": "選擇背景音樂",
            "type": "select",
            "options": music_options,
            "required": True
        })
        fields.append({
            "name": "custom_audio",
            "label": "上傳自訂音樂檔案",
            "type": "file",
            "multiple": False,
            "accept": "audio/*",
            "required": False,
            "conditional": "music=custom"
        })
        
        templates.append({
            "id": t_id,
            "name": f"✨ [自訂] {ct.get('name')}",
            "description": f"{ct.get('description', '')} (比例: {ct.get('aspect_ratio', '9:16')}, 共 {len(ct.get('scenes', []))} 個場景)",
            "preview_url": "/static/templates/promo_preview.mp4",
            "fields": fields
        })
        
    return templates

def get_audio_path(selection: str, custom_file_path: str = None) -> str:
    if selection == "custom":
        return custom_file_path
    elif selection.startswith("library:"):
        filename = selection.split("library:")[1]
        return get_library_file_path(filename)
    else:
        return os.path.join(LIBRARY_MUSIC_DIR, selection)

def run_render_in_thread(task_id: str, template_id: str, params: Dict[str, Any], file_paths: Dict[str, Any]):
    """Background rendering coordinator running in a separate thread/process context."""
    output_filename = f"output_{task_id}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    try:
        if template_id == "slideshow":
            images = file_paths.get("images", [])
            title = params.get("title", "")
            music_selection = params.get("music", "library:ambient.mp3")
            
            bg_music = get_audio_path(music_selection, file_paths.get("custom_audio", None))
                
            video_processor.generate_slideshow_video(
                task_id, images, title, bg_music, output_path, update_task_progress
            )
            
        elif template_id == "meme":
            video_path = file_paths.get("video", "")
            top_text = params.get("top_text", "")
            bottom_text = params.get("bottom_text", "")
            
            video_processor.generate_meme_video(
                task_id, video_path, top_text, bottom_text, output_path, update_task_progress
            )
            
        elif template_id == "intro":
            logo = file_paths.get("logo", "")
            brand_name = params.get("brand_name", "")
            tagline = params.get("tagline", "")
            sound_selection = params.get("sound", "library:cinematic.mp3")
            
            bg_music = get_audio_path(sound_selection, file_paths.get("custom_audio", None))
                
            video_processor.generate_logo_intro_video(
                task_id, logo, brand_name, tagline, bg_music, output_path, update_task_progress
            )
            
        elif template_id == "product_promo":
            images = file_paths.get("images", [])
            brand_name = params.get("brand_name", "")
            product_name = params.get("product_name", "")
            highlights = [
                params.get("highlight1", ""),
                params.get("highlight2", ""),
                params.get("highlight3", "")
            ]
            music_selection = params.get("music", "library:tech.mp3")
            
            bg_music = get_audio_path(music_selection, file_paths.get("custom_audio", None))
                
            video_processor.generate_product_promo_video(
                task_id, images, brand_name, product_name, highlights, bg_music, output_path, update_task_progress
            )
            
        elif template_id.startswith("custom_"):
            db = load_db()
            custom_tpl = db.get("custom_templates", {}).get(template_id)
            if not custom_tpl:
                raise ValueError(f"Custom template {template_id} not found.")
                
            # Deep copy to avoid modifying the database in memory
            import copy
            custom_tpl = copy.deepcopy(custom_tpl)
            
            # Override text contents from request parameters
            for idx, scene in enumerate(custom_tpl.get("scenes", [])):
                for t_idx, text in enumerate(scene.get("texts", [])):
                    param_name = f"scene_{idx}_text_{t_idx}"
                    if param_name in params:
                        text["content"] = params[param_name]
                        
            music_selection = params.get("music", "library:ambient.mp3")
            bg_music = get_audio_path(music_selection, file_paths.get("custom_audio", None))
                
            video_processor.generate_custom_template_video(
                task_id, custom_tpl, file_paths, bg_music, output_path, update_task_progress
            )
            
        else:
            raise ValueError(f"Unknown template ID: {template_id}")
            
        # Mark task as completed
        tasks_status[task_id]["status"] = "completed"
        tasks_status[task_id]["progress"] = 100
        tasks_status[task_id]["message"] = "渲染成功！您的影片已就緒。"
        tasks_status[task_id]["output_url"] = f"/outputs/{output_filename}"
        
        # Record completed video in metadata database
        try:
            db = load_db()
            template_names = {
                "slideshow": "時尚相簿投影片",
                "meme": "迷因短片",
                "intro": "品牌 Logo 片頭",
                "product_promo": "高質感商品宣傳短片"
            }
            t_name = template_names.get(template_id, "未命名影片")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            db["videos"][output_filename] = {
                "filename": output_filename,
                "name": f"{t_name} - {datetime.now().strftime('%m%d_%H%M')}",
                "memo": f"使用「{t_name}」範本於 {timestamp} 製作完成。",
                "url": f"/outputs/{output_filename}",
                "template_id": template_id,
                "created_at": timestamp
            }
            save_db(db)
        except Exception as ex:
            print(f"Error saving output video metadata: {ex}")
        
    except Exception as e:
        print(f"Error rendering task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["message"] = f"影片生成失敗: {str(e)}"
        tasks_status[task_id]["error"] = str(e)


@app.post("/api/render")
async def start_render(
    request: Request,
    background_tasks: BackgroundTasks,
    template_id: str = Form(...),
):
    # Standard forms and multipart files
    form_data = await request.form()
    task_id = str(uuid.uuid4())
    
    # Initialize task status
    tasks_status[task_id] = {
        "status": "pending",
        "progress": 0,
        "message": "排隊中，準備上傳與剪輯...",
        "output_url": None,
        "error": None
    }
    
    params = {}
    file_paths = {}
    
    try:
        # Resolve library file selections first (*_library parameters)
        for key in list(form_data.keys()):
            if key.endswith("_library"):
                orig_key = key[:-8]  # Strip "_library"
                val_str = form_data.get(key)
                if val_str:
                    filenames = [f.strip() for f in val_str.split(",") if f.strip()]
                    resolved_paths = [get_library_file_path(f) for f in filenames]
                    
                    if orig_key == "images":
                        file_paths[orig_key] = resolved_paths
                    else:
                        file_paths[orig_key] = resolved_paths[0] if resolved_paths else ""

        # Extract fields and save files correctly (avoiding reading streams twice)
        keys_processed = set()
        for key in form_data.keys():
            if key == "template_id" or key in keys_processed or key.endswith("_library"):
                continue
            
            keys_processed.add(key)
            values = form_data.getlist(key)
            if not values:
                continue
                
            # Check if this key holds file upload(s)
            if hasattr(values[0], "filename"):
                # Save uploaded files persistently into LIBRARY_DIR subfolders
                if len(values) > 1 or key == "images":
                    saved_paths = []
                    db = load_db()
                    for idx, upload_file in enumerate(values):
                        if upload_file.filename:
                            ext = os.path.splitext(upload_file.filename)[1]
                            temp_filename = f"{task_id}_{key}_{idx}_{uuid.uuid4().hex[:6]}{ext}"
                            
                            f_type = get_file_type(temp_filename)
                            if f_type == "image":
                                temp_path = os.path.join(LIBRARY_PHOTOS_DIR, temp_filename)
                                url_path = f"/library/photos/{temp_filename}"
                            elif f_type == "video":
                                temp_path = os.path.join(LIBRARY_MOVIES_DIR, temp_filename)
                                url_path = f"/library/movies/{temp_filename}"
                            else: # audio
                                temp_path = os.path.join(LIBRARY_MUSIC_DIR, temp_filename)
                                url_path = f"/library/music/{temp_filename}"
                                
                            with open(temp_path, "wb") as buffer:
                                shutil.copyfileobj(upload_file.file, buffer)
                            saved_paths.append(temp_path)
                            
                            db["assets"][temp_filename] = {
                                "filename": temp_filename,
                                "name": upload_file.filename,
                                "memo": "",
                                "type": f_type,
                                "url": url_path,
                                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                    save_db(db)
                    if saved_paths:
                        file_paths[key] = saved_paths
                else:
                    upload_file = values[0]
                    if upload_file.filename:
                        ext = os.path.splitext(upload_file.filename)[1]
                        temp_filename = f"{task_id}_{key}_{uuid.uuid4().hex[:6]}{ext}"
                        
                        f_type = get_file_type(temp_filename)
                        if f_type == "image":
                            temp_path = os.path.join(LIBRARY_PHOTOS_DIR, temp_filename)
                            url_path = f"/library/photos/{temp_filename}"
                        elif f_type == "video":
                            temp_path = os.path.join(LIBRARY_MOVIES_DIR, temp_filename)
                            url_path = f"/library/movies/{temp_filename}"
                        else: # audio
                            temp_path = os.path.join(LIBRARY_MUSIC_DIR, temp_filename)
                            url_path = f"/library/music/{temp_filename}"
                            
                        with open(temp_path, "wb") as buffer:
                            shutil.copyfileobj(upload_file.file, buffer)
                        file_paths[key] = temp_path
                        
                        db = load_db()
                        db["assets"][temp_filename] = {
                            "filename": temp_filename,
                            "name": upload_file.filename,
                            "memo": "",
                            "type": f_type,
                            "url": url_path,
                            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        save_db(db)
            else:
                # Text parameter
                params[key] = values[-1]
                
        # Start background processing
        background_tasks.add_task(
            run_render_in_thread, task_id, template_id, params, file_paths
        )
        
        return {"task_id": task_id}
        
    except Exception as e:
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["message"] = f"提交失敗: {str(e)}"
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_status[task_id]


from pydantic import BaseModel

class UpdateItem(BaseModel):
    category: str  # "assets" | "videos"
    id: str        # filename
    name: str
    memo: str

@app.post("/api/library/upload")
async def upload_library_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
        
    ext = os.path.splitext(file.filename)[1]
    task_id = str(uuid.uuid4())
    temp_filename = f"uploaded_{task_id[:8]}_{uuid.uuid4().hex[:6]}{ext}"
    
    file_type = get_file_type(temp_filename)
    if file_type == "image":
        temp_path = os.path.join(LIBRARY_PHOTOS_DIR, temp_filename)
        url_path = f"/library/photos/{temp_filename}"
    elif file_type == "video":
        temp_path = os.path.join(LIBRARY_MOVIES_DIR, temp_filename)
        url_path = f"/library/movies/{temp_filename}"
    else: # audio
        temp_path = os.path.join(LIBRARY_MUSIC_DIR, temp_filename)
        url_path = f"/library/music/{temp_filename}"
        
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        db = load_db()
        db["assets"][temp_filename] = {
            "filename": temp_filename,
            "name": file.filename,
            "memo": "手動上傳的素材",
            "type": file_type,
            "url": url_path,
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_db(db)
        return {"status": "success", "filename": temp_filename}
    except Exception as e:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/library")
async def get_library():
    db = load_db()
    assets_list = list(db.get("assets", {}).values())
    videos_list = list(db.get("videos", {}).values())
    
    # Sort by date descending
    assets_list.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
    videos_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {"assets": assets_list, "videos": videos_list}

@app.post("/api/library/update")
async def update_library_item(item: UpdateItem):
    db = load_db()
    category = item.category
    item_id = item.id
    
    if category not in ["assets", "videos"]:
        raise HTTPException(status_code=400, detail="Invalid category")
        
    if item_id not in db[category]:
        raise HTTPException(status_code=404, detail="Item not found")
        
    db[category][item_id]["name"] = item.name
    db[category][item_id]["memo"] = item.memo
    save_db(db)
    return {"status": "success"}

@app.delete("/api/library/{category}/{item_id}")
async def delete_library_item(category: str, item_id: str):
    db = load_db()
    if category not in ["assets", "videos"]:
        raise HTTPException(status_code=400, detail="Invalid category")
        
    if item_id not in db[category]:
        raise HTTPException(status_code=404, detail="Item not found")
        
    filename = db[category][item_id]["filename"]
    if category == "assets":
        file_path = get_library_file_path(filename)
    else:
        file_path = os.path.join(OUTPUT_DIR, filename)
        
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
            
    del db[category][item_id]
    save_db(db)
    return {"status": "success"}


class CustomTemplate(BaseModel):
    id: str = None
    name: str
    description: str
    aspect_ratio: str  # "16:9" | "9:16"
    transition_effect: str = "none"  # "none" | "fade" | "crossfade"
    scenes: List[Dict[str, Any]]

@app.get("/api/templates/custom/{template_id}")
async def get_custom_template(template_id: str):
    db = load_db()
    custom_tpl = db.get("custom_templates", {}).get(template_id)
    if not custom_tpl:
        raise HTTPException(status_code=404, detail="Custom template not found")
    return custom_tpl

@app.delete("/api/templates/custom/{template_id}")
async def delete_custom_template(template_id: str):
    db = load_db()
    if "custom_templates" in db and template_id in db["custom_templates"]:
        del db["custom_templates"][template_id]
        save_db(db)
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Custom template not found")

@app.post("/api/templates/custom")
async def create_custom_template(ct: CustomTemplate):
    db = load_db()
    if "custom_templates" not in db:
        db["custom_templates"] = {}
        
    t_id = ct.id if ct.id else f"custom_{uuid.uuid4().hex[:8]}"
    
    scenes_list = []
    for idx, scene in enumerate(ct.scenes):
        visual_type = scene.get("visual_type", "image_zoom")
        scenes_list.append({
            "duration": float(scene.get("duration", 3.0)),
            "visual_type": visual_type,
            "zoom_direction": scene.get("zoom_direction", "in"),
            "color": scene.get("color", "#000000"),
            "audio_option": scene.get("audio_option", "keep"),
            "audio_volume": float(scene.get("audio_volume", 1.0)),
            "enable_text": bool(scene.get("enable_text", True)),
            "asset_field": f"scene_{idx}_file" if visual_type != "solid_color" else "",
            "texts": scene.get("texts", [])
        })
        
    existing_created_at = db["custom_templates"].get(t_id, {}).get("created_at")
    created_at = existing_created_at if existing_created_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    db["custom_templates"][t_id] = {
        "id": t_id,
        "name": ct.name,
        "description": ct.description,
        "aspect_ratio": ct.aspect_ratio,
        "transition_effect": ct.transition_effect,
        "scenes": scenes_list,
        "created_at": created_at,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_db(db)
    return {"status": "success", "template_id": t_id}


class GenerateEffectRequest(BaseModel):
    tool: str  # "image_blend" | "image_filter" | "multi_transition"
    params: Dict[str, Any]

def run_effect_render_in_thread(task_id: str, tool: str, params: Dict[str, Any]):
    ext = ".mp3" if tool == "audio_handler" and params.get("audio_action") == "extract" else ".mp4"
    output_filename = f"output_{task_id}{ext}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    try:
        if tool == "image_blend":
            img1 = params.get("image1")
            img2 = params.get("image2")
            duration = float(params.get("duration", 5.0))
            fade_duration = float(params.get("fade_duration", 1.0))
            
            video_processor.generate_blend_effect_video(
                task_id, img1, img2, duration, fade_duration, output_path, update_task_progress
            )
        elif tool == "image_filter":
            img = params.get("image")
            filter_type = params.get("filter_type", "ken_burns")
            duration = float(params.get("duration", 4.0))
            
            video_processor.generate_filter_effect_video(
                task_id, img, filter_type, duration, output_path, update_task_progress
            )
        elif tool == "multi_transition":
            images = params.get("images", [])
            transition_type = params.get("transition_type", "crossfade")
            slide_duration = float(params.get("slide_duration", 3.0))
            transition_duration = float(params.get("transition_duration", 1.0))
            
            video_processor.generate_multi_transition_video(
                task_id, images, transition_type, slide_duration, transition_duration, output_path, update_task_progress
            )
        elif tool == "alpha_blend":
            media1 = params.get("media1")
            media2 = params.get("media2")
            opacity = float(params.get("opacity", 0.5))
            duration = float(params.get("duration", 5.0))
            
            video_processor.generate_alpha_blend_video(
                task_id, media1, media2, opacity, duration, output_path, update_task_progress
            )
        elif tool == "grid_layout":
            medias = params.get("medias", [])
            cols = int(params.get("cols", 2))
            rows = int(params.get("rows", 2))
            duration = float(params.get("duration", 5.0))
            gap = int(params.get("gap", 4))
            
            video_processor.generate_grid_layout_video(
                task_id, medias, cols, rows, duration, gap, output_path, update_task_progress
            )
        elif tool == "audio_handler":
            video_path = params.get("video")
            audio_action = params.get("audio_action")
            
            update_task_progress(task_id, 20, f"正在載入影片並進行音訊處理 ({'靜音' if audio_action == 'mute' else '提取音軌'})...")
            
            video_processor.process_media_tool_temp(
                input_file_path=video_path,
                action=audio_action,
                output_path=output_path
            )
            
            update_task_progress(task_id, 100, "處理完成！您現在可以選擇將其儲存至媒體中心。")
        else:
            raise ValueError(f"Unknown effect tool type: {tool}")
            
        tasks_status[task_id]["status"] = "completed"
        tasks_status[task_id]["progress"] = 100
        tasks_status[task_id]["message"] = "特效影片生成成功！"
        tasks_status[task_id]["output_url"] = f"/outputs/{output_filename}"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["message"] = f"處理失敗: {str(e)}"

@app.post("/api/effects/generate")
async def generate_effect(req: GenerateEffectRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks_status[task_id] = {
        "status": "processing",
        "progress": 0,
        "message": "已接收特效生成任務...",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    resolved_params = {}
    for k, v in req.params.items():
        if isinstance(v, str) and v.startswith("library:"):
            filename = v.split("library:")[1]
            resolved_params[k] = get_library_file_path(filename)
        elif isinstance(v, list):
            resolved_list = []
            for item in v:
                if isinstance(item, str) and item.startswith("library:"):
                    filename = item.split("library:")[1]
                    resolved_list.append(get_library_file_path(filename))
                else:
                    resolved_list.append(item)
            resolved_params[k] = resolved_list
        else:
            resolved_params[k] = v
            
    background_tasks.add_task(
        run_effect_render_in_thread, task_id, req.tool, resolved_params
    )
    return {"status": "success", "task_id": task_id}


class SaveEffectToLibraryRequest(BaseModel):
    task_id: str
    name: str
    memo: str = ""

@app.post("/api/effects/save-to-library")
async def save_effect_to_library(req: SaveEffectToLibraryRequest):
    task = tasks_status.get(req.task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=400, detail="任務尚未完成或不存在")
        
    output_url = task.get("output_url")
    orig_filename = os.path.basename(output_url)
    src_path = os.path.join(OUTPUT_DIR, orig_filename)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="產生的效果檔案不存在")
        
    ext = os.path.splitext(orig_filename)[1].lower()
    
    if ext == ".mp3":
        dest_filename = f"effect_{uuid.uuid4().hex[:6]}_{orig_filename}"
        dest_path = os.path.join(LIBRARY_DIR, "music", dest_filename)
        db_type = "audio"
        url_path = f"/library/music/{dest_filename}"
    else:
        dest_filename = f"effect_{uuid.uuid4().hex[:6]}_{orig_filename}"
        dest_path = os.path.join(LIBRARY_DIR, "movies", dest_filename)
        db_type = "video"
        url_path = f"/library/movies/{dest_filename}"
        
    import shutil
    try:
        shutil.copy(src_path, dest_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"複製檔案失敗: {str(e)}")
        
    db = load_db()
    db["assets"][dest_filename] = {
        "filename": dest_filename,
        "name": req.name,
        "memo": req.memo or "由特效工坊生成之成果。",
        "type": db_type,
        "url": url_path,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_db(db)
    return {"status": "success", "filename": dest_filename}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, lifespan="on", reload=True)

