import os
import time
import requests
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# Render ke Environment Variables se values uthayega
# Agar local testing kar rahe hain to fallback values use hongi
API_ID = int(os.environ.get("API_ID", 31266551))
API_HASH = os.environ.get("API_HASH", "f2ebfd089cc0958fbedad2088fdc917b")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8765142201:AAHuJ3EpQ83NAcozShmIXqoH7JnXCIE9Oi8")

DM_API_KEY = os.environ.get("DM_API_KEY", "ce70a9ac41a3aad3c8a4")
DM_API_SECRET = os.environ.get("DM_API_SECRET", "8fe3500e687d7f9b03e740964b01fb1e0156da1c")
DM_USERNAME = os.environ.get("DM_USERNAME", "nareshduran99@gmail.com")
DM_PASSWORD = os.environ.get("DM_PASSWORD", "@naresh9982483529")

app = Client(
    "dm_uploader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


def get_dm_access_token():
    url = "https://api.dailymotion.com/oauth/token"
    payload = {
        "grant_type": "password",
        "client_id": DM_API_KEY,
        "client_secret": DM_API_SECRET,
        "username": DM_USERNAME,
        "password": DM_PASSWORD,
        "scope": "manage_videos"
    }
    res = requests.post(url, data=payload).json()
    if "access_token" in res:
        return res["access_token"]
    raise Exception(f"Dailymotion Login Fail: {res}")


def upload_to_dailymotion(file_path: str, title: str):
    token = get_dm_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    upload_url_res = requests.get("https://api.dailymotion.com/file/upload", headers=headers).json()
    upload_url = upload_url_res.get("upload_url")
    if not upload_url:
        raise Exception(f"Upload URL error: {upload_url_res}")

    with open(file_path, "rb") as f:
        upload_res = requests.post(upload_url, files={"file": f}).json()

    uploaded_url = upload_res.get("url")
    if not uploaded_url:
        raise Exception(f"File upload fail: {upload_res}")

    create_url = "https://api.dailymotion.com/me/videos"
    payload = {
        "url": uploaded_url,
        "title": title,
        "published": "true",
        "channel": "fun"
    }
    video_res = requests.post(create_url, headers=headers, data=payload).json()
    video_id = video_res.get("id")

    if not video_id:
        raise Exception(f"Video publish fail: {video_res}")

    return {
        "id": video_id,
        "stream_link": f"https://www.dailymotion.com/video/{video_id}",
        "embed_link": f"https://www.dailymotion.com/embed/video/{video_id}"
    }


async def progress(current, total, message: Message, start_time, action_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        elapsed_time = round(diff)
        eta = round((total - current) / speed) if speed > 0 else 0

        text = (
            f"🔄 **{action_name}...**\n\n"
            f"📊 **Progress:** `{percentage:.1f}%`\n"
            f"📦 **Size:** `{current / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB`\n"
            f"⚡ **Speed:** `{speed / (1024 * 1024):.2f} MB/s`\n"
            f"⏳ **ETA:** `{eta}s`"
        )
        try:
            await message.edit_text(text)
        except Exception:
            pass


@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    await message.reply_text(
        "👋 **Namaste! Main Dailymotion Uploader Bot hoon.**\n\n"
        "📹 Mujhe koi bhi video bhejo (upto 2GB).\n"
        "• Title video se auto nikal jayega\n"
        "• Dailymotion par direct upload hoga\n"
        "• Streaming aur download/embed link mil jayega!"
    )


@app.on_message((filters.video | filters.document) & filters.private)
async def video_handler(client: Client, message: Message):
    media = message.video or message.document

    if message.document and not (message.document.mime_type and message.document.mime_type.startswith("video/")):
        return

    status_msg = await message.reply_text("⚡ Download shuru ho raha hai...", quote=True)

    if message.caption:
        video_title = message.caption.strip()
    elif hasattr(media, "file_name") and media.file_name:
        video_title = os.path.splitext(media.file_name)[0]
    else:
        video_title = f"Video_{media.file_unique_id}"

    start_time = time.time()
    file_path = f"downloads/{media.file_unique_id}.mp4"
    os.makedirs("downloads", exist_ok=True)

    try:
        await message.download(
            file_name=file_path,
            progress=progress,
            progress_args=(status_msg, start_time, "Downloading from Telegram")
        )

        await status_msg.edit_text(
            f"🚀 **Title:** `{video_title}`\n\n"
            "📤 Dailymotion par upload ho raha hai, thoda intezar karein..."
        )

        loop = asyncio.get_event_loop()
        dm_data = await loop.run_in_executor(None, upload_to_dailymotion, file_path, video_title)

        final_text = (
            f"✅ **Dailymotion par Upload Ho Gaya!**\n\n"
            f"🎬 **Title:** `{video_title}`\n"
            f"🆔 **Video ID:** `{dm_data['id']}`\n\n"
            f"▶️ **Online Streaming Link:**\n{dm_data['stream_link']}\n\n"
            f"📥 **Player / Embed Link:**\n{dm_data['embed_link']}"
        )
        await status_msg.edit_text(final_text, disable_web_page_preview=False)

    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** `{str(e)}`")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    print("🤖 Dailymotion MTProto Bot Running on Render...")
    app.run()
