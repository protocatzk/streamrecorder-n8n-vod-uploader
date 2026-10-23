import os
import asyncio
import logging
from aiohttp import web, ClientSession
from telethon import TelegramClient
from dotenv import load_dotenv, find_dotenv

# 1. Lade .env Datei falls vorhanden (sucht im aktuellen Ordner und übergeordneten Ordnern)
dotenv_file = find_dotenv(usecwd=True)
if dotenv_file:
    load_dotenv(dotenv_file)
else:
    load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('vod_uploader')

# 2. Liest ausschließlich aus Umgebungsvariablen (Betriebssystem / Docker) oder aus .env
API_ID_RAW = os.getenv('TELEGRAM_API_ID')
if not API_ID_RAW:
    raise ValueError("TELEGRAM_API_ID Umgebungsvariable oder in .env fehlt!")
API_ID = int(API_ID_RAW)

API_HASH = os.getenv('TELEGRAM_API_HASH')
if not API_HASH:
    raise ValueError("TELEGRAM_API_HASH Umgebungsvariable oder in .env fehlt!")

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN Umgebungsvariable oder in .env fehlt!")

DEFAULT_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
if not DEFAULT_CHAT_ID:
    raise ValueError("TELEGRAM_CHAT_ID Umgebungsvariable oder in .env fehlt!")

logger.info(f"Konfiguration geladen (API_ID: {API_ID}, Default Chat: {DEFAULT_CHAT_ID})")

async def download_video(url: str, output_path: str):
    logger.info(f"Starte Download von: {url[:80]}... nach {output_path}")
    async with ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Download fehlgeschlagen mit HTTP {response.status}")
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(output_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(2 * 1024 * 1024):  # 2MB Chunks
                    f.write(chunk)
                    downloaded += len(chunk)
            logger.info(f"Download fertig: {downloaded} Bytes heruntergeladen ({round(downloaded/1024/1024, 1)} MB).")

async def handle_upload(request):
    client = request.app['telegram_client']
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    download_url = data.get("download_url")
    if not download_url:
        return web.json_response({"error": "Missing download_url"}, status=400)

    raw_chat_id = data.get("chat_id", DEFAULT_CHAT_ID)
    try:
        chat_id = int(raw_chat_id)
    except ValueError:
        chat_id = raw_chat_id

    streamer = data.get("streamer", "Unbekannt")
    title = data.get("title", "Livestream Recording")
    duration = data.get("duration", "N/A")
    filesize_mb = data.get("filesize_mb", "N/A")
    recording_id = data.get("recording_id", "")

    caption = (
        f"🎥 <b>Neues Stream-Recording</b>\n\n"
        f"👤 <b>Streamer:</b> {streamer}\n"
        f"📌 <b>Titel:</b> {title}\n"
        f"⏱ <b>Dauer:</b> {duration}\n"
        f"💾 <b>Größe:</b> {filesize_mb} MB\n"
        f"🆔 <b>ID:</b><code> {recording_id}</code>"
    )

    temp_filename = f"/tmp/stream_{recording_id or os.getpid()}.mp4"

    try:
        # 1. Video herunterladen
        await download_video(download_url, temp_filename)

        # 2. Upload via Telegram Client
        logger.info(f"Starte Upload zu Chat {chat_id}...")
        message = await client.send_file(
            entity=chat_id,
            file=temp_filename,
            caption=caption,
            parse_mode='html',
            supports_streaming=True
        )
        logger.info(f"Upload erfolgreich! Message ID: {message.id}")

        return web.json_response({
            "status": "success",
            "message_id": message.id,
            "chat_id": chat_id
        })

    except Exception as e:
        logger.error(f"Fehler bei Verarbeitung: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
                logger.info(f"Temporäre Datei {temp_filename} gelöscht.")
            except Exception as e:
                logger.warning(f"Konnte Temp-Datei nicht löschen: {e}")

async def handle_health(request):
    return web.json_response({
        "status": "ok",
        "bot": "Ripperbot",
        "chat_id": DEFAULT_CHAT_ID
    })

async def on_startup(app):
    # Wichtig: Client muss in derselben Event Loop gestartet werden, in der aiohttp läuft
    app['telegram_client'] = TelegramClient('vod_bot_session', API_ID, API_HASH)
    await app['telegram_client'].start(bot_token=BOT_TOKEN)
    logger.info("Telegram Bot Client erfolgreich im aiohttp Event-Loop gestartet!")

async def on_cleanup(app):
    client = app.get('telegram_client')
    if client:
        await client.disconnect()
        logger.info("Telegram Bot Client getrennt.")

def create_app():
    app = web.Application()
    app.router.add_post('/upload', handle_upload)
    app.router.add_get('/health', handle_health)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080)
