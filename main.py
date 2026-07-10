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
UPLOAD_DIR = os.path.join(WORKSPACE_DIR, "uploads")
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "outputs")
STATIC_DIR = os.path.join(WORKSPACE_DIR, "static")
TEMPLATES_DIR = os.path.join(STATIC_DIR, "templates")
ASSETS_DIR = os.path.join(STATIC_DIR, "assets")
LIBRARY_DIR = os.path.join(STATIC_DIR, "library")

for directory in [UPLOAD_DIR, OUTPUT_DIR, STATIC_DIR, TEMPLATES_DIR, ASSETS_DIR, LIBRARY_DIR]:
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
    # Pre-generate preview videos programmatically on start
    print("Initializing system assets and default preview videos...")
    
    # 1. Asynchronously download royalty-free background music tracks
    urls = {
        "upbeat_electro.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "chill_vibes.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "acoustic_peace.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
    }
    
    loop = asyncio.get_event_loop()
    for filename, url in urls.items():
        dest = os.path.join(ASSETS_DIR, filename)
        if not os.path.exists(dest):
            loop.run_in_executor(None, download_audio_asset, url, dest)
            
    # 2. Generate ambient/tech/cinematic synth files for user selections
    music_tracks = {
        "ambient.mp3": lambda t: np.sin(2 * np.pi * 220 * t) * 0.4 + np.sin(2 * np.pi * 275 * t) * 0.3,
        "tech.mp3": lambda t: np.sin(2 * np.pi * 440 * (t % 0.25 < 0.1) * t) * 0.3 + np.sin(2 * np.pi * 880 * (t % 0.25 < 0.05) * t) * 0.2,
        "cinematic.mp3": lambda t: np.sin(2 * np.pi * 110 * t) * 0.5 * (1 - np.exp(-t)) + np.sin(2 * np.pi * 165 * t) * 0.4
    }
    
    import numpy as np
    from moviepy.audio.AudioClip import AudioClip
    
    for filename, wave_func in music_tracks.items():
        path = os.path.join(ASSETS_DIR, filename)
        if not os.path.exists(path):
            try:
                print(f"Generating audio asset: {filename}...")
                tone = AudioClip(wave_func, duration=30.0, fps=44100)
                tone.write_audiofile(path, fps=44100, logger=None)
                tone.close()
            except Exception as e:
                print(f"Failed to generate synth {filename}: {e}")
                
    # 3. Initialize templates
    try:
        video_processor.generate_default_previews(TEMPLATES_DIR, ASSETS_DIR)
    except Exception as e:
        print(f"Error generating preview templates: {e}")

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/api/templates")
async def get_templates():
    # Dynamically scan static/assets for mp3 files
    mp3_options = []
    if os.path.exists(ASSETS_DIR):
        for f in os.listdir(ASSETS_DIR):
            if f.endswith(".mp3"):
                name_without_ext = os.path.splitext(f)[0]
                label = name_without_ext.replace("_", " ").title()
                
                custom_labels = {
                    "upbeat_electro": "輕快動感電音 (推薦)",
                    "chill_vibes": "放鬆律動音樂 (推薦)",
                    "acoustic_peace": "溫馨和平吉他 (推薦)",
                    "ambient": "靈動氛圍音樂 (內建合成)",
                    "tech": "科技感電子樂 (內建合成)",
                    "cinematic": "磅礡電影音效 (內建合成)",
                    "default_audio": "預設簡短提示音 (內建合成)"
                }
                
                display_label = custom_labels.get(name_without_ext, label)
                mp3_options.append({"value": f, "label": display_label})
                
    # Sort options to put recommended ones first, then others
    def sort_key(opt):
        val = opt["value"]
        if "upbeat" in val or "chill" in val or "acoustic" in val:
            return (0, val)
        elif "default_audio" in val:
            return (2, val)
        else:
            return (1, val)
            
    mp3_options.sort(key=sort_key)
    
    # Add standard custom file upload option at the end
    music_options = list(mp3_options) + [{"value": "custom", "label": "自行上傳音訊檔案 (.mp3/.wav)"}]
    sound_options = list(mp3_options) + [{"value": "custom", "label": "自行上傳音效檔案 (.mp3/.wav)"}]
    
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
    return templates

def run_render_in_thread(task_id: str, template_id: str, params: Dict[str, Any], file_paths: Dict[str, Any]):
    """Background rendering coordinator running in a separate thread/process context."""
    output_filename = f"output_{task_id}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    try:
        if template_id == "slideshow":
            images = file_paths.get("images", [])
            title = params.get("title", "")
            music_selection = params.get("music", "ambient.mp3")
            
            if music_selection == "custom":
                bg_music = file_paths.get("custom_audio", None)
            else:
                bg_music = os.path.join(ASSETS_DIR, music_selection)
                
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
            sound_selection = params.get("sound", "cinematic.mp3")
            
            if sound_selection == "custom":
                bg_music = file_paths.get("custom_audio", None)
            else:
                bg_music = os.path.join(ASSETS_DIR, sound_selection)
                
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
            music_selection = params.get("music", "tech.mp3")
            
            if music_selection == "custom":
                bg_music = file_paths.get("custom_audio", None)
            else:
                bg_music = os.path.join(ASSETS_DIR, music_selection)
                
            video_processor.generate_product_promo_video(
                task_id, images, brand_name, product_name, highlights, bg_music, output_path, update_task_progress
            )
            
        else:
            raise ValueError(f"Unknown template ID: {template_id}")
            
        # Clean up temporary uploaded files (only those in uploads, not library)
        for key, val in file_paths.items():
            if isinstance(val, list):
                for path in val:
                    if os.path.exists(path) and UPLOAD_DIR in path:
                        try: os.remove(path)
                        except Exception: pass
            elif isinstance(val, str) and val and os.path.exists(val) and UPLOAD_DIR in val:
                try: os.remove(val)
                except Exception: pass
                
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
        # Extract fields and save files correctly (avoiding reading streams twice)
        keys_processed = set()
        for key in form_data.keys():
            if key == "template_id" or key in keys_processed:
                continue
            
            keys_processed.add(key)
            values = form_data.getlist(key)
            if not values:
                continue
                
            # Check if this key holds file upload(s)
            if hasattr(values[0], "filename"):
                # Save uploaded files persistently into LIBRARY_DIR
                if len(values) > 1 or key == "images":
                    saved_paths = []
                    db = load_db()
                    for idx, upload_file in enumerate(values):
                        if upload_file.filename:
                            ext = os.path.splitext(upload_file.filename)[1]
                            temp_filename = f"{task_id}_{key}_{idx}_{uuid.uuid4().hex[:6]}{ext}"
                            temp_path = os.path.join(LIBRARY_DIR, temp_filename)
                            with open(temp_path, "wb") as buffer:
                                shutil.copyfileobj(upload_file.file, buffer)
                            saved_paths.append(temp_path)
                            
                            db["assets"][temp_filename] = {
                                "filename": temp_filename,
                                "name": upload_file.filename,
                                "memo": "",
                                "type": get_file_type(temp_filename),
                                "url": f"/library/{temp_filename}",
                                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                    save_db(db)
                    file_paths[key] = saved_paths
                else:
                    upload_file = values[0]
                    if upload_file.filename:
                        ext = os.path.splitext(upload_file.filename)[1]
                        temp_filename = f"{task_id}_{key}_{uuid.uuid4().hex[:6]}{ext}"
                        temp_path = os.path.join(LIBRARY_DIR, temp_filename)
                        with open(temp_path, "wb") as buffer:
                            shutil.copyfileobj(upload_file.file, buffer)
                        file_paths[key] = temp_path
                        
                        db = load_db()
                        db["assets"][temp_filename] = {
                            "filename": temp_filename,
                            "name": upload_file.filename,
                            "memo": "",
                            "type": get_file_type(temp_filename),
                            "url": f"/library/{temp_filename}",
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
        file_path = os.path.join(LIBRARY_DIR, filename)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, lifespan="on", reload=True)

