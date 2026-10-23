import os
import glob
import math
import asyncio
import logging
import uuid
from aiohttp import web, ClientSession, ClientTimeout
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

# Maximale Dateigröße vor dem Aufteilen (1.8 GB) und Zielgröße pro Segment (1.7 GB)
SPLIT_THRESHOLD_BYTES = int(1.8 * 1024 * 1024 * 1024)   # 1.8 GB = 1.932.735.283 Bytes
TARGET_PART_SIZE_BYTES = int(1.7 * 1024 * 1024 * 1024)  # 1.7 GB = 1.825.361.100 Bytes

logger.info(f"Konfiguration geladen (API_ID: {API_ID}, Default Chat: {DEFAULT_CHAT_ID}, Split-Schwelle: 1.8 GB)")

PLATFORM_ICONS = {
    'tiktok': '📱 TikTok',
    'twitch': '🟣 Twitch',
    'kick': '🟢 Kick',
    'youtube': '🔴 YouTube'
}

async def download_file(url: str, output_path: str):
    logger.info(f"Starte Download von: {url[:80]}... nach {output_path}")
    # Kein Gesamt-Timeout (total=None), damit auch mehrstündige/große Downloads nicht abbrechen
    timeout = ClientTimeout(total=None, sock_read=300, sock_connect=60)
    async with ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Download fehlgeschlagen mit HTTP {response.status}")
            
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            last_logged_mb = 0
            with open(output_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(2 * 1024 * 1024):  # 2MB Chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    mb = downloaded // (100 * 1024 * 1024)
                    if mb > last_logged_mb:
                        last_logged_mb = mb
                        pct = f" ({round(downloaded / total_size * 100)}%)" if total_size else ""
                        logger.info(f"Download Fortschritt: {round(downloaded / (1024*1024))} MB{pct}")
                        
            logger.info(f"Download fertig: {downloaded} Bytes heruntergeladen ({round(downloaded/1024/1024, 1)} MB).")

def parse_duration_str(d_str: str) -> float | None:
    if not d_str or d_str == "N/A":
        return None
    try:
        parts = [float(p) for p in d_str.strip().split(':')]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
    except Exception:
        pass
    return None

async def get_video_duration(file_path: str) -> float | None:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            val = float(stdout.decode().strip())
            if val > 0:
                return val
    except Exception as e:
        logger.warning(f"ffprobe konnte Dauer nicht ermitteln: {e}")
    return None

async def split_video(file_path: str, job_id: str, num_parts: int, duration_sec: float) -> list[str]:
    segment_time = duration_sec / num_parts
    output_pattern = f"/tmp/part_{job_id}_%03d.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", file_path,
        "-c", "copy",
        "-map", "0",
        "-f", "segment",
        "-segment_time", f"{segment_time:.2f}",
        "-reset_timestamps", "1",
        output_pattern
    ]
    logger.info(f"[{job_id}] Starte ffmpeg-Splitting in {num_parts} Teile (je ~{segment_time:.1f}s)...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode('utf-8', errors='ignore')
        logger.error(f"[{job_id}] ffmpeg-Fehler: {err_msg}")
        raise Exception(f"Video-Aufteilung fehlgeschlagen: {err_msg[:200]}")
    
    glob_pattern = f"/tmp/part_{job_id}_*.mp4"
    parts = sorted(glob.glob(glob_pattern))
    if not parts:
        raise Exception("ffmpeg erzeugte keine Part-Dateien!")
    logger.info(f"[{job_id}] Splitting erfolgreich: {len(parts)} Teile erzeugt.")
    return parts

async def handle_upload(request):
    app = request.app
    client = app['telegram_client']
    lock = app['upload_lock']

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    download_url = data.get("download_url")
    if not download_url:
        return web.json_response({"error": "Missing download_url"}, status=400)

    recording_id = str(data.get("recording_id", ""))
    job_id = recording_id or str(uuid.uuid4())[:8]
    streamer = data.get("streamer", "Unbekannt")
    title = data.get("title", "Livestream Recording")

    app['waiting_count'] += 1
    in_queue = True
    logger.info(f"[{job_id}] Request in Warteschlange eingereiht ({streamer} - '{title}'). Wartende Jobs: {app['waiting_count']}.")

    temp_video = f"/tmp/stream_{job_id}.mp4"
    temp_thumb = f"/tmp/thumb_{job_id}.jpg" if data.get("thumbnail_url") else None
    split_parts = []

    try:
        async with lock:
            in_queue = False
            app['waiting_count'] -= 1
            logger.info(f"[{job_id}] Bearbeitung gestartet! (Verbleibend in Queue: {app['waiting_count']})")

            raw_chat_id = data.get("chat_id", DEFAULT_CHAT_ID)
            try:
                chat_id = int(raw_chat_id)
            except ValueError:
                chat_id = raw_chat_id

            duration = data.get("duration", "N/A")
            filesize_mb = data.get("filesize_mb", "N/A")
            thumbnail_url = data.get("thumbnail_url")
            platform = data.get("platform", "").lower()
            category = data.get("category", "")
            max_viewers = data.get("max_viewers")
            avg_viewers = data.get("avg_viewers")
            deletion_time = data.get("deletion_time", "")

            # 1. Thumbnail parallel/vorab laden
            if thumbnail_url:
                try:
                    await download_file(thumbnail_url, temp_thumb)
                    logger.info(f"[{job_id}] Thumbnail erfolgreich geladen.")
                except Exception as e:
                    logger.warning(f"[{job_id}] Thumbnail konnte nicht geladen werden, fahre ohne fort: {e}")
                    temp_thumb = None

            # 2. Video herunterladen
            await download_file(download_url, temp_video)

            actual_size = os.path.getsize(temp_video)
            actual_size_mb = round(actual_size / (1024 * 1024), 1)
            logger.info(f"[{job_id}] Download abgeschlossen. Tatsächliche Größe: {actual_size_mb} MB")

            platform_label = PLATFORM_ICONS.get(platform, f"🌐 {platform.capitalize() if platform else 'Stream'}")
            upload_files = []

            # 3. Prüfen ob Aufteilung nötig (> 1.8 GB)
            if actual_size > SPLIT_THRESHOLD_BYTES:
                num_parts = max(2, math.ceil(actual_size / TARGET_PART_SIZE_BYTES))
                logger.info(f"[{job_id}] Datei ({actual_size_mb} MB) überschreitet 1.8 GB Limit! Teile in {num_parts} Teile auf.")

                duration_sec = await get_video_duration(temp_video)
                if not duration_sec:
                    duration_sec = parse_duration_str(duration)
                if not duration_sec:
                    duration_sec = num_parts * 900  # Fallback

                split_parts = await split_video(temp_video, job_id, num_parts, duration_sec)

                # Teil 1 mit allen Infos/Stats
                caption_lines = [
                    f"🎥 <b>Neues Stream-Recording (Teil 1/{len(split_parts)})</b>\n",
                    f"👤 <b>Streamer:</b> {streamer}",
                    f"📌 <b>Titel:</b> {title}"
                ]
                if category:
                    caption_lines.append(f"🎮 <b>Kategorie:</b> {category} | {platform_label}")
                else:
                    caption_lines.append(f"📡 <b>Plattform:</b> {platform_label}")

                caption_lines.append("")
                caption_lines.append(f"⏱ <b>Gesamtdauer:</b> {duration}")
                caption_lines.append(f"💾 <b>Gesamtgröße:</b> {actual_size_mb} MB ({len(split_parts)} Teile)")

                if max_viewers and max_viewers > 0:
                    caption_lines.append(f"👥 <b>Zuschauer:</b> Peak: {max_viewers:,} | Ø {avg_viewers:,}".replace(',', '.'))

                if deletion_time:
                    caption_lines.append(f"⏳ <b>Cloud-Speicher:</b> noch {deletion_time}")

                caption_lines.append(f"🆔 <b>ID:</b> <code>{recording_id}</code>")
                main_caption = "\n".join(caption_lines)
                upload_files.append((split_parts[0], main_caption))

                # Teil 2..N nummeriert
                for idx, part_path in enumerate(split_parts[1:], start=2):
                    sub_caption = (
                        f"🎥 <b>Neues Stream-Recording (Teil {idx}/{len(split_parts)})</b>\n\n"
                        f"👤 <b>Streamer:</b> {streamer}\n"
                        f"📌 <b>Titel:</b> {title}\n"
                        f"🆔 <b>ID:</b> <code>{recording_id}</code>"
                    )
                    upload_files.append((part_path, sub_caption))
            else:
                caption_lines = [
                    f"🎥 <b>Neues Stream-Recording</b>\n",
                    f"👤 <b>Streamer:</b> {streamer}",
                    f"📌 <b>Titel:</b> {title}"
                ]
                if category:
                    caption_lines.append(f"🎮 <b>Kategorie:</b> {category} | {platform_label}")
                else:
                    caption_lines.append(f"📡 <b>Plattform:</b> {platform_label}")

                caption_lines.append("")
                caption_lines.append(f"⏱ <b>Dauer:</b> {duration}")
                caption_lines.append(f"💾 <b>Größe:</b> {filesize_mb} MB")

                if max_viewers and max_viewers > 0:
                    caption_lines.append(f"👥 <b>Zuschauer:</b> Peak: {max_viewers:,} | Ø {avg_viewers:,}".replace(',', '.'))

                if deletion_time:
                    caption_lines.append(f"⏳ <b>Cloud-Speicher:</b> noch {deletion_time}")

                caption_lines.append(f"🆔 <b>ID:</b> <code>{recording_id}</code>")
                caption = "\n".join(caption_lines)
                upload_files.append((temp_video, caption))

            # 4. Upload zu Telegram
            uploaded_message_ids = []
            for file_to_upload, file_caption in upload_files:
                file_mb = round(os.path.getsize(file_to_upload) / (1024 * 1024), 1)
                logger.info(f"[{job_id}] Sende {os.path.basename(file_to_upload)} ({file_mb} MB) zu Chat {chat_id}...")

                last_reported_pct = -1
                def make_progress_callback(f_name):
                    nonlocal last_reported_pct
                    def callback(current, total):
                        nonlocal last_reported_pct
                        pct = int(current / total * 100) if total else 0
                        if pct >= last_reported_pct + 25:
                            last_reported_pct = (pct // 25) * 25
                            logger.info(f"[{job_id}] Upload {f_name}: {last_reported_pct}% ({round(current/(1024*1024))} / {round(total/(1024*1024))} MB)")
                    return callback

                msg = await client.send_file(
                    entity=chat_id,
                    file=file_to_upload,
                    caption=file_caption,
                    thumb=temp_thumb if temp_thumb and os.path.exists(temp_thumb) else None,
                    parse_mode='html',
                    supports_streaming=True,
                    progress_callback=make_progress_callback(os.path.basename(file_to_upload))
                )
                uploaded_message_ids.append(msg.id)
                logger.info(f"[{job_id}] Upload erfolgreich! Message ID: {msg.id}")

            return web.json_response({
                "status": "success",
                "message_id": uploaded_message_ids[0],
                "message_ids": uploaded_message_ids,
                "parts": len(uploaded_message_ids),
                "chat_id": chat_id
            })

    except Exception as e:
        logger.error(f"[{job_id}] Fehler bei Verarbeitung: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

    finally:
        if in_queue:
            app['waiting_count'] -= 1

        # 5. Sauberes Aufräumen aller temporären Dateien
        for part_file in split_parts:
            if part_file and os.path.exists(part_file):
                try:
                    os.remove(part_file)
                    logger.info(f"[{job_id}] Temporäre Part-Datei gelöscht: {part_file}")
                except Exception as e:
                    logger.warning(f"[{job_id}] Konnte Part-Datei nicht löschen: {e}")

        for temp_file in [temp_video, temp_thumb]:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"[{job_id}] Temporäre Datei gelöscht: {temp_file}")
                except Exception as e:
                    logger.warning(f"[{job_id}] Konnte Temp-Datei nicht löschen: {e}")

async def handle_health(request):
    app = request.app
    lock = app.get('upload_lock')
    is_busy = lock.locked() if lock else False
    return web.json_response({
        "status": "ok",
        "bot": "Ripperbot",
        "busy": is_busy,
        "queue_length": app.get('waiting_count', 0),
        "split_threshold_mb": 1800,
        "chat_id": DEFAULT_CHAT_ID
    })

async def on_startup(app):
    app['upload_lock'] = asyncio.Lock()
    app['waiting_count'] = 0
    app['telegram_client'] = TelegramClient('vod_bot_session', API_ID, API_HASH)
    await app['telegram_client'].start(bot_token=BOT_TOKEN)
    logger.info("Telegram Bot Client und Queue-Lock erfolgreich im aiohttp Event-Loop gestartet!")

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
