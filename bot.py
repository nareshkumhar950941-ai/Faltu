import os
import sys
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# 1. Render Web Service ke liye Chota Health-Check Server (Port binding)
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

# Background thread me HTTP server chalayein
threading.Thread(target=run_http_server, daemon=True).start()

# 2. Asyncio event loop ensure karein
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.environ.get("API_ID", "31266551"))
API_HASH = os.environ.get("API_HASH", "f2ebfd089cc0958fbedad2088fdc917b")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8765142201:AAHuJ3EpQ83NAcozShmIXqoH7JnXCIE9Oi8")

DM_API_KEY = os.environ.get("DM_API_KEY", "ce70a9ac41a3aad3c8a4")
DM_API_SECRET = os.environ.get("DM_API_SECRET", "8fe3500e687d7f9b03e740964b01fb1e0156da1c")
DM_USERNAME = os.environ.get("DM_USERNAME", "nareshduran99@gmail.com")
DM_PASSWORD = os.environ.get("DM_PASSWORD", "@Nareshbhi9982")

app = Client("dm_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_dm_access_token():
    auth_url = "https://api.dailymotion.com/oauth/token"
    data = {
        "grant_type": "password",
        "client_id": DM_API_KEY,
        "client_secret": DM_API_SECRET,
        "username": DM_USERNAME,
        "password": DM_PASSWORD,
        "scope": "manage_videos"
    }
    r = requests.post(auth_url, data=data, timeout=30)
    res = r.json()
    if "access_token" in res:
        return res["access_token"]
    raise Exception(f"Dailymotion login fail: {res}")

def upload_to_dailymotion(file_path: str, title: str):
    token = get_dm_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Upload URL prapt karein
    upload_url_res = requests.get(
        "https://api.dailymotion.com/file/upload",
        headers=headers,
        timeout=30
    ).json()

    if "upload_url" not in upload_url_res:
        raise Exception(f"Upload URL fail: {upload_url_res}")

    upload_url = upload_url_res["upload_url"]

    # File upload karein Dailymotion par
    with open(file_path, "rb") as f:
        up_res = requests.post(upload_url, files={"file": f}, timeout=1800).json()

    file_result_url = up_res.get("url")
    if not file_result_url:
        raise Exception(f"File upload fail: {up_res}")

    # Video publish karein
    clean_title = (title or "Uploaded Video")[:250].strip()
    create_payload = {
        "url": file_result_url,
        "title": clean_title,
        "channel": "news",
        "is_created_for_kids": "false",
        "published": "true"
    }

    create_res = requests.post(
        "https://api.dailymotion.com/me/videos",
        headers=headers,
        data=create_payload,
        timeout=30
    ).json()

    if "id" not in create_res:
        raise Exception(f"Video publish fail: {create_res}")

    video_id = create_res["id"]
    watch_url = f"https://www.dailymotion.com/video/{video_id}"
    embed_url = f"https://www.dailymotion.com/embed/video/{video_id}"

    return watch_url, embed_url

@app.on_message(filters.command("start"))
async def start_cmd(_, msg: Message):
    print(f"Received /start from {msg.chat.id}")
    await msg.reply_text("👋 Namaste! Bot live hai. Mujhe koi bhi video forward ya send karein, main use Dailymotion par upload kar dunga.")

@app.on_message(filters.video | filters.document)
async def handle_video(_, msg: Message):
    media = msg.video or msg.document
    if not media:
        return

    if msg.document and not (media.mime_type and media.mime_type.startswith("video/")):
        return

    title = msg.caption or getattr(media, "file_name", None) or "Telegram Video"
    print(f"Processing video: {title}")
    status_msg = await msg.reply_text("⏳ 1/2 Video Telegram se download ho rahi hai...")

    download_path = None
    try:
        download_path = await msg.download()
        await status_msg.edit_text("📤 2/2 Dailymotion par upload aur publish ho rahi hai...")

        loop = asyncio.get_event_loop()
        watch_url, embed_url = await loop.run_in_executor(
            None, upload_to_dailymotion, download_path, title
        )

        reply_text = (
            f"✅ **Video Upload Ho Gayi!**\n\n"
            f"📌 **Title:** {title}\n"
            f"🔗 **Watch Link:** {watch_url}\n"
            f"📺 **Embed Link:** {embed_url}"
        )
        await status_msg.edit_text(reply_text, disable_web_page_preview=False)
        print("Upload successful!")

    except Exception as e:
        print(f"Error occurred: {e}")
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass

@app.on_message(filters.text & ~filters.command("start"))
async def handle_other_text(_, msg: Message):
    await msg.reply_text("Bot active hai! Kripya koi video bhejein ya forward karein.")

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
