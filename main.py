
import os
import telebot
import asyncio
from telethon import TelegramClient
from flask import Flask, jsonify
from threading import Thread
import aiohttp
import nest_asyncio
nest_asyncio.apply()
app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TERABOX_API_URL = os.getenv("TERABOX_API_URL")
bot = telebot.TeleBot(BOT_TOKEN)
telethon_client = TelegramClient("bot_session", API_ID, API_HASH)
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200
@bot.message_handler(commands=["start"])
def start_command(message):
    try:
        bot.send_message(
            message.chat.id,
            "Hello! Send me a valid Terabox link, and I'll process it for you."
        )
    except Exception as e:
        print(f"Error in /start command: {str(e)}")
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not url.startswith("http"):
        bot.reply_to(message, "Please send a valid URL.")
        return
    try:
        msg = bot.send_message(message.chat.id, "Processing your request...")
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        print(f"Error deleting message: {str(e)}")
    asyncio.create_task(process_file(url, message))
async def process_file(url, message):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TERABOX_API_URL}?url={url}") as resp:
                if resp.status != 200:
                    bot.reply_to(message, "Failed to fetch file details. Please check the link.")
                    return
                data = await resp.json()
        if not data.get("ok"):
            bot.reply_to(message, "Failed to fetch file details. Please check the link.")
            return
        filename = data["filename"]
        download_url = data["downloadLink"]
        file_size = data["size"]
        try:
            file_size_mb = float(file_size.replace("MB", "").strip())
        except ValueError:
            bot.reply_to(message, "Could not determine file size. Please try another link.")
            return
        max_size_mb = 2000
        if file_size_mb > max_size_mb:
            bot.reply_to(message, f"File size exceeds Telegram's 2GB limit: {file_size}.")
            return
        bot.reply_to(message, f"Downloading: {filename} ({file_size})")
        os.makedirs("./downloads", exist_ok=True)
        file_path = os.path.join("./downloads", f"{message.chat.id}_{filename}")
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    bot.reply_to(message, "Failed to download the file.")
                    return
                with open(file_path, "wb") as file:
                    while chunk := await resp.content.read(1024 * 1024):
                        file.write(chunk)
        bot.reply_to(message, f"Download complete: {filename}")
        with open(file_path, "rb") as file:
            if filename.endswith(('.mp4', '.mkv', '.avi')):
                bot.send_video(message.chat.id, file, caption=f"Here is your video: {filename}")
            else:
                bot.send_document(message.chat.id, file, caption=f"Here is your file: {filename}")
        asyncio.create_task(upload_to_channel(file_path, filename))
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
async def upload_to_channel(file_path, filename):
    try:
        if not telethon_client.is_connected():
            await telethon_client.connect()
        await telethon_client.send_file(
            CHANNEL_ID,
            file_path,
            caption=f"Uploaded: {filename}"
        )
    except Exception as e:
        print(f"Error uploading file to channel: {str(e)}")
if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=5000)
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    async def main():
        try:
            await telethon_client.start(bot_token=BOT_TOKEN)
            print("Bot is running...")
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            print(f"Error starting bot: {str(e)}")
    asyncio.run(main())
  
