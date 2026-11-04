import asyncio
import http.server
import logging
import os
import threading
import time
from pyrogram import Client, filters
from pyrogram.types import Message
import requests
from requests_toolbelt.multipart.encoder import (
    MultipartEncoder,
    MultipartEncoderMonitor,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# ================= CREDENTIALS =================
# Aap Render Dashboard -> Environment Variables me ye keys set kar sakte hain,
# ya fir yahan quotes (" ") ke andar apni actual values daal sakte hain:
API_ID = int(os.environ.get("API_ID", "YOUR_TELEGRAM_API_ID"))
API_HASH = os.environ.get("API_HASH", "YOUR_TELEGRAM_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

DM_API_KEY = os.environ.get("DM_API_KEY", "YOUR_DAILYMOTION_API_KEY")
DM_API_SECRET = os.environ.get("DM_API_SECRET", "YOUR_DAILYMOTION_API_SECRET")
DM_USERNAME = os.environ.get("DM_USERNAME", "YOUR_DAILYMOTION_EMAIL")
DM_PASSWORD = os.environ.get("DM_PASSWORD", "YOUR_DAILYMOTION_PASSWORD")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ================= HELPER FUNCTIONS =================
def human_size(num_bytes):
  """Bytes ko KB/MB/GB me convert karta hai"""
  if not num_bytes:
    return "0 B"
  for unit in ["B", "KB", "MB", "GB", "TB"]:
    if num_bytes < 1024.0:
      return f"{num_bytes:.2f} {unit}"
    num_bytes /= 1024.0
  return f"{num_bytes:.2f} PB"


def human_time(seconds):
  """Time ko seconds/minutes me format karta hai"""
  seconds = int(seconds)
  if seconds <= 0:
    return "0s"
  if seconds < 60:
    return f"{seconds}s"
  elif seconds < 3600:
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s"
  else:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}s"


def make_bar(percentage):
  """Progress bar banata hai [████░░░░░░]"""
  percentage = max(0.0, min(100.0, percentage))
  filled = int(percentage / 10)
  return "█" * filled + "░" * (10 - filled)


async def safe_edit(message: Message, text: str):
  """Telegram message rate limit se bachane ke liye safe edit"""
  try:
    await message.edit_text(text)
  except Exception:
    pass


# ================= PROGRESS CALLBACKS =================
async def download_progress(current, total, status_msg, start_time, last_update):
  now = time.time()
  # Telegram FloodWait se bachne ke liye har 3.5 second me update karega
  if (now - last_update[0] < 3.5) and (current < total):
    return
  last_update[0] = now

  elapsed = now - start_time
  speed = current / elapsed if elapsed > 0 else 0
  percentage = (current / total) * 100 if total > 0 else 0
  eta = (total - current) / speed if speed > 0 else 0

  bar = make_bar(percentage)

  text = (
      f"📥 **Downloading from Telegram...**\n\n"
      f"`[{bar}]` **{percentage:.1f}%**\n\n"
      f"⚡ **Speed:** `{human_size(speed)}/s`\n"
      f"📊 **Progress:** `{human_size(current)}` / `{human_size(total)}`\n"
      f"⏳ **ETA:** `{human_time(eta)}`"
  )
  await safe_edit(status_msg, text)


def upload_to_dailymotion_with_progress(
    upload_url, file_path, status_msg, loop
):
  start_time = time.time()
  last_update = [0]

  def on_progress(monitor):
    now = time.time()
    current = monitor.bytes_read
    total = monitor.len

    if (now - last_update[0] < 3.5) and (current < total):
      return
    last_update[0] = now

    elapsed = now - start_time
    speed = current / elapsed if elapsed > 0 else 0
    percentage = (current / total) * 100 if total > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0

    bar = make_bar(percentage)

    text = (
        f"📤 **Uploading to Dailymotion...**\n\n"
        f"`[{bar}]` **{percentage:.1f}%**\n\n"
        f"⚡ **Speed:** `{human_size(speed)}/s`\n"
        f"📊 **Progress:** `{human_size(current)}` / `{human_size(total)}`\n"
        f"⏳ **ETA:** `{human_time(eta)}`"
    )
    asyncio.run_coroutine_threadsafe(safe_edit(status_msg, text), loop)

  with open(file_path, "rb") as f:
    encoder = MultipartEncoder(
        fields={
            "file": (
                os.path.basename(file_path),
                f,
                "video/mp4",
            )
        }
    )
    monitor = MultipartEncoderMonitor(encoder, on_progress)
    headers = {"Content-Type": monitor.content_type}

    resp = requests.post(
        upload_url, data=monitor, headers=headers, timeout=3600
    )
    data = resp.json()
    if "url" not in data:
      raise Exception(f"Upload URL response error: {data}")
    return data["url"]


# ================= DAILYMOTION API =================
def get_dm_token():
  data = {
      "grant_type": "password",
      "client_id": DM_API_KEY,
      "client_secret": DM_API_SECRET,
      "username": DM_USERNAME,
      "password": DM_PASSWORD,
      "scope": "manage_videos",
  }
  r = requests.post(
      "https://api.dailymotion.com/oauth/token", data=data, timeout=30
  )
  res = r.json()
  if "access_token" not in res:
    raise Exception(
        f"Dailymotion Login Fail: {res.get('error_description', res)}"
    )
  return res["access_token"]


def get_dm_upload_url(token):
  headers = {"Authorization": f"Bearer {token}"}
  r = requests.get(
      "https://api.dailymotion.com/file/upload", headers=headers, timeout=30
  )
  res = r.json()
  if "upload_url" not in res:
    raise Exception(f"Upload URL nahi mila: {res}")
  return res["upload_url"]


def create_dm_video(token, file_url, title):
  headers = {"Authorization": f"Bearer {token}"}
  payload = {
      "url": file_url,
      "title": title[:240],
      "is_created_for_kids": "false",
      "published": "true",
      "channel": "news",
  }
  r = requests.post(
      "https://api.dailymotion.com/me/videos",
      data=payload,
      headers=headers,
      timeout=60,
  )
  res = r.json()
  if "id" in res:
    return res["id"]

  # Fallback if channel/params give error
  r2 = requests.post(
      "https://api.dailymotion.com/me/videos",
      data={"url": file_url, "title": title[:240]},
      headers=headers,
      timeout=60,
  )
  res2 = r2.json()
  if "id" in res2:
    vid = res2["id"]
    requests.post(
        f"https://api.dailymotion.com/video/{vid}",
        data={"published": "true", "is_created_for_kids": "false"},
        headers=headers,
        timeout=30,
    )
    return vid
  raise Exception(f"Video publish fail: {res}")


# ================= RENDER HEALTH SERVER =================
def start_health_server():
  port = int(os.environ.get("PORT", 8080))

  class HealthHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
      self.send_response(200)
      self.end_headers()
      self.wfile.write(b"Bot is online and working!")

    def log_message(self, *args):
      return

  server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
  t = threading.Thread(target=server.serve_forever, daemon=True)
  t.start()
  logging.info(f"Health server listening on port {port}")


# ================= TELEGRAM BOT =================
bot = Client("dm_uploader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@bot.on_message(filters.command("start"))
async def start_handler(client, message: Message):
  await message.reply_text(
      "👋 **Namaste!**\n\nMujhe koi bhi video ya file bhejo, main use real-time speed ke sath download karke direct Dailymotion par upload kar dunga!"
  )


@bot.on_message(filters.video | filters.document)
async def process_video(client, message: Message):
  media = message.video or message.document
  if not media:
    return

  # Video ka Title nikalna
  title = "Untitled Video"
  if message.caption:
    title = message.caption
  elif hasattr(media, "file_name") and media.file_name:
    title = os.path.splitext(media.file_name)[0]

  status_msg = await message.reply_text("⏳ **Process shuru ho raha hai...**")
  download_path = None
  loop = asyncio.get_running_loop()

  try:
    # 1. Download with real-time speed & progress
    start_time = time.time()
    last_update = [0]

    download_path = await message.download(
        progress=download_progress,
        progress_args=(status_msg, start_time, last_update),
    )

    await safe_edit(
        status_msg, "🔑 **Dailymotion se connect ho raha hai...**"
    )

    # 2. Dailymotion Token & Upload URL
    token = await asyncio.to_thread(get_dm_token)
    upload_url = await asyncio.to_thread(get_dm_upload_url, token)

    # 3. Upload with real-time speed & progress
    await safe_edit(status_msg, "📤 **Upload shuru ho raha hai...**")
    file_url = await asyncio.to_thread(
        upload_to_dailymotion_with_progress,
        upload_url,
        download_path,
        status_msg,
        loop,
    )

    # 4. Create and publish
    await safe_edit(status_msg, "🎬 **Video publish ho rahi hai...**")
    video_id = await asyncio.to_thread(create_dm_video, token, file_url, title)

    video_url = f"https://www.dailymotion.com/video/{video_id}"
    embed_url = f"https://geo.dailymotion.com/player/x1a2b.html?video={video_id}"

    result_text = (
        f"✅ **Upload Safal Hua!**\n\n"
        f"📌 **Title:** `{title}`\n"
        f"📦 **Size:** `{human_size(media.file_size)}`\n\n"
        f"🔗 **Watch Link:**\n{video_url}\n\n"
        f"📺 **Stream / Player Link:**\n{embed_url}"
    )
    await safe_edit(status_msg, result_text)

  except Exception as e:
    logging.exception("Error in process_video")
    await safe_edit(status_msg, f"❌ **Error aa gaya:**\n`{str(e)}`")

  finally:
    # Render storage full hone se bachane ke liye local file delete karein
    if download_path and os.path.exists(download_path):
      try:
        os.remove(download_path)
      except Exception:
        pass


if __name__ == "__main__":
  start_health_server()
  logging.info("Starting Telegram Bot...")
  bot.run()
