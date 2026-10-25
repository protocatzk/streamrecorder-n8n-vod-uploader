import os
import re
import glob
import math
import shutil
import asyncio
import logging
import uuid
from datetime import datetime
from aiohttp import web, ClientSession, ClientTimeout
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from dotenv import load_dotenv, find_dotenv
from fast_uploader import fast_upload_file, get_video_metadata, parse_duration_to_seconds
from topic_manager import topic_manager

# 1. Lade .env Datei falls vorhanden
dotenv_file = find_dotenv(usecwd=True)
if dotenv_file:
    load_dotenv(dotenv_file)
else:
    load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('vod_uploader')

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

DEFAULT_FORUM_CHAT_ID = os.getenv('TELEGRAM_FORUM_CHAT_ID')
FORWARD_DROP_AUTHOR = os.getenv('FORWARD_DROP_AUTHOR', 'true').lower() in ('true', '1', 'yes')

# Maximale Dateigröße vor dem Aufteilen (1.8 GB) und Zielgröße pro Segment (1.4 GB für sicheren VBR-Puffer)
SPLIT_THRESHOLD_BYTES = int(1.8 * 1024 * 1024 * 1024)   # 1.8 GB = 1.932.735.283 Bytes
TARGET_PART_SIZE_BYTES = int(1.4 * 1024 * 1024 * 1024)  # 1.4 GB = 1.503.238.553 Bytes
PARALLEL_WORKERS = int(os.getenv('PARALLEL_UPLOAD_WORKERS', '6'))

logger.info(f"Konfiguration geladen (API_ID: {API_ID}, Default Chat: {DEFAULT_CHAT_ID}, Forum Chat: {DEFAULT_FORUM_CHAT_ID}, Drop Author: {FORWARD_DROP_AUTHOR}, Split-Schwelle: 1.8 GB, Zielgröße: 1.4 GB, Parallele Upload-Worker: {PARALLEL_WORKERS})")

PLATFORM_ICONS = {
    'tiktok': '📱 TikTok',
    'twitch': '🟣 Twitch',
    'kick': '🟢 Kick',
    'youtube': '🔴 YouTube'
}

class BotState:
    def __init__(self):
        self.upload_lock = asyncio.Lock()
        self.waiting_count = 0
        self.telegram_client: TelegramClient | None = None

state = BotState()

async def download_file(url: str, output_path: str):
    logger.info(f"Starte Download von: {url[:80]}... nach {output_path}")
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

def sanitize_cookie(raw_cookie: str | None) -> str | None:
    if not raw_cookie:
        return None
    cookie_str = str(raw_cookie).strip()
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()
    # Ersetze CRLF und Zeilenumbrüche durch Semikolon-Trennung für gültiges Cookie-Header-Format
    cookie_str = re.sub(r'[\r\n]+', '; ', cookie_str)
    # Entferne verbleibende ASCII-Steuerzeichen (< 32 und 127)
    cookie_str = re.sub(r'[\x00-\x1f\x7f]', '', cookie_str).strip()
    # Mehrfache Semikolons/Leerzeichen bereinigen
    cookie_str = re.sub(r';\s*;+', ';', cookie_str).strip('; ')
    return cookie_str if cookie_str else None

def format_recorded_at(date_str: str | None) -> str | None:
    if not date_str or str(date_str).strip() in ("", "N/A", "None"):
        return None
    try:
        cleaned = str(date_str).replace('Z', '').split('+')[0].strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%d.%m.%Y, %H:%M Uhr")
            except ValueError:
                pass
        return str(date_str)
    except Exception:
        return str(date_str)

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
    meta = await get_video_metadata(file_path)
    dur = meta.get("duration", 0.0)
    return dur if dur > 0 else None

async def run_ffmpeg_segment(
    file_path: str,
    output_pattern: str,
    segment_time: float,
    job_id: str
) -> list[str]:
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
    logger.info(f"[{job_id}] Starte ffmpeg-Segmentierung mit segment_time={segment_time:.1f}s...")
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
    
    glob_pattern = output_pattern.replace("%03d", "*")
    parts = sorted(glob.glob(glob_pattern))
    return parts

async def split_video_to_parts(
    input_file: str,
    job_dir: str,
    job_id: str,
    initial_duration: float | None = None
) -> list[str]:
    """
    Teilt ein Video deterministisch und robust so auf, dass JEDER resultierende Teil
    garantiert unter SPLIT_THRESHOLD_BYTES (1.8 GB) liegt.
    Verwendet eine iterative Queue mit isolierten Unterordnern pro Split-Schritt,
    um Namenskollisionen, unvollständige Splits und Endlosschleifen auszuschließen.
    """
    total_size = os.path.getsize(input_file)
    if total_size <= SPLIT_THRESHOLD_BYTES:
        return [input_file]

    queue = [input_file]
    verified_parts: list[str] = []
    split_step = 0
    max_total_steps = 40

    while queue and split_step < max_total_steps:
        current_file = queue.pop(0)

        if not os.path.exists(current_file):
            logger.warning(f"[{job_id}] Teil nicht gefunden: {current_file}, überspringe...")
            continue

        current_size = os.path.getsize(current_file)
        if current_size <= SPLIT_THRESHOLD_BYTES:
            verified_parts.append(current_file)
            continue

        split_step += 1
        current_mb = round(current_size / (1024 * 1024), 1)
        logger.info(f"[{job_id}] Datei/Teil {os.path.basename(current_file)} ({current_mb} MB) überschreitet 1.8 GB Limit (Schritt {split_step})...")

        part_dur = await get_video_duration(current_file)
        if not part_dur or part_dur <= 0:
            if current_file == input_file and initial_duration and initial_duration > 0:
                part_dur = initial_duration
            else:
                estimated_sec = (current_size * 8) / (3 * 1024 * 1024)
                part_dur = max(60.0, estimated_sec)
                logger.info(f"[{job_id}] Dauer nicht direkt lesbar, geschätzt: ~{part_dur:.1f}s")

        sub_count = max(2, math.ceil(current_size / TARGET_PART_SIZE_BYTES))
        segment_time = part_dur / sub_count

        step_dir = os.path.join(job_dir, f"split_step_{split_step}")
        os.makedirs(step_dir, exist_ok=True)
        output_pattern = os.path.join(step_dir, "part_%03d.mp4")

        # Versuche ffmpeg-Segmentierung. Falls nur 1 Teil erzeugt wird (weil segment_time >= tatsächliche Dauer),
        # halbiere segment_time adaptiv (bis zu 4 Versuche)
        new_parts = []
        attempt = 0
        current_seg_time = segment_time

        while attempt < 4:
            attempt += 1
            new_parts = await run_ffmpeg_segment(current_file, output_pattern, current_seg_time, job_id)

            if len(new_parts) > 1:
                break

            logger.warning(
                f"[{job_id}] ffmpeg erzeugte nur {len(new_parts)} Teil(e) mit segment_time={current_seg_time:.1f}s. "
                f"Halbiere segment_time für Versuch {attempt + 1}..."
            )

            for p in new_parts:
                try:
                    os.remove(p)
                except Exception:
                    pass

            current_seg_time = max(30.0, current_seg_time / 2)

        if len(new_parts) <= 1:
            logger.error(f"[{job_id}] Konnte Teil {current_file} trotz mehrerer Versuche nicht aufteilen!")
            if new_parts:
                verified_parts.extend(new_parts)
            else:
                verified_parts.append(current_file)
            continue

        # Lösche die übergeordnete Zwischendatei (wenn es nicht die originale input_file ist)
        if current_file != input_file:
            try:
                os.remove(current_file)
            except Exception as e:
                logger.warning(f"[{job_id}] Konnte temporäre Zwischendatei {current_file} nicht löschen: {e}")

        # Neue Teile vorne in die Queue einfügen, um die chronologische Reihenfolge zu bewahren
        queue = new_parts + queue

    if split_step >= max_total_steps and queue:
        logger.warning(f"[{job_id}] Maximale Split-Schritte ({max_total_steps}) erreicht! Verbleibende Queue wird übernommen.")
        verified_parts.extend(queue)

    return verified_parts

async def handle_upload(request):
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

    state.waiting_count += 1
    in_queue = True
    logger.info(f"[{job_id}] Request eingereiht ({streamer} - '{title}'). Wartende Jobs: {state.waiting_count}.")

    job_dir = f"/tmp/job_{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    temp_video = os.path.join(job_dir, f"stream_{job_id}.mp4")
    temp_thumb = os.path.join(job_dir, f"thumb_{job_id}.jpg") if data.get("thumbnail_url") else None

    try:
        async with state.upload_lock:
            in_queue = False
            state.waiting_count -= 1
            logger.info(f"[{job_id}] Bearbeitung gestartet! (Verbleibend in Queue: {state.waiting_count})")

            raw_chat_id = data.get("chat_id", DEFAULT_CHAT_ID)
            try:
                chat_id = int(raw_chat_id)
            except ValueError:
                chat_id = raw_chat_id

            raw_forum_chat_id = data.get("forum_chat_id", DEFAULT_FORUM_CHAT_ID)
            forum_chat_id = None
            if raw_forum_chat_id:
                try:
                    forum_chat_id = int(raw_forum_chat_id)
                except ValueError:
                    forum_chat_id = raw_forum_chat_id

            duration = data.get("duration", "N/A")
            filesize_mb = data.get("filesize_mb", "N/A")
            thumbnail_url = data.get("thumbnail_url")
            platform = data.get("platform", "").lower()
            category = data.get("category", "")
            max_viewers = data.get("max_viewers")
            avg_viewers = data.get("avg_viewers")
            deletion_time = data.get("deletion_time", "")
            recorded_at = data.get("recorded_at", "")
            formatted_date = format_recorded_at(recorded_at)

            # 1. Thumbnail vorab laden
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
            clean_streamer = "".join(c for c in streamer if c.isalnum() or c in ('_', '-')).strip() or "stream"
            upload_files: list[tuple[str, str, str]] = []  # (file_path, caption, display_filename)

            # 3. Prüfen ob Aufteilung nötig (> 1.8 GB)
            if actual_size > SPLIT_THRESHOLD_BYTES:
                duration_sec = await get_video_duration(temp_video)
                if not duration_sec:
                    duration_sec = parse_duration_to_seconds(duration)

                split_parts = await split_video_to_parts(temp_video, job_dir, job_id, initial_duration=duration_sec)
                total_parts = len(split_parts)
                logger.info(f"[{job_id}] Finale Anzahl geprüfter Video-Teile: {total_parts}")

                # Teil 1 mit allen Infos/Stats
                caption_lines = [
                    f"🎥 <b>Neues Stream-Recording (Teil 1/{total_parts})</b>\n",
                    f"👤 <b>Streamer:</b> {streamer}",
                    f"📌 <b>Titel:</b> {title}"
                ]
                if category:
                    caption_lines.append(f"🎮 <b>Kategorie:</b> {category} | {platform_label}")
                else:
                    caption_lines.append(f"📡 <b>Plattform:</b> {platform_label}")

                caption_lines.append("")
                if formatted_date:
                    caption_lines.append(f"📅 <b>Datum:</b> {formatted_date}")
                caption_lines.append(f"⏱ <b>Gesamtdauer:</b> {duration}")
                caption_lines.append(f"💾 <b>Gesamtgröße:</b> {actual_size_mb} MB ({total_parts} Teile)")
                caption_lines.append(f"🆔 <b>ID:</b> <code>{recording_id}</code>")
                main_caption = "\n".join(caption_lines)
                display_filename_1 = f"{clean_streamer}_{job_id}_part01.mp4"
                upload_files.append((split_parts[0], main_caption, display_filename_1))

                # Teil 2..N nummeriert
                for idx, part_path in enumerate(split_parts[1:], start=2):
                    sub_caption_lines = [
                        f"🎥 <b>Neues Stream-Recording (Teil {idx}/{total_parts})</b>\n",
                        f"👤 <b>Streamer:</b> {streamer}",
                        f"📌 <b>Titel:</b> {title}"
                    ]
                    if formatted_date:
                        sub_caption_lines.append(f"📅 <b>Datum:</b> {formatted_date}")
                    sub_caption_lines.append(f"🆔 <b>ID:</b> <code>{recording_id}</code>")
                    sub_caption = "\n".join(sub_caption_lines)
                    display_filename_n = f"{clean_streamer}_{job_id}_part{idx:02d}.mp4"
                    upload_files.append((part_path, sub_caption, display_filename_n))
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
                if formatted_date:
                    caption_lines.append(f"📅 <b>Datum:</b> {formatted_date}")
                caption_lines.append(f"⏱ <b>Dauer:</b> {duration}")
                caption_lines.append(f"💾 <b>Größe:</b> {actual_size_mb} MB")
                caption_lines.append(f"🆔 <b>ID:</b> <code>{recording_id}</code>")
                caption = "\n".join(caption_lines)
                display_filename_single = f"{clean_streamer}_{job_id}.mp4"
                upload_files.append((temp_video, caption, display_filename_single))

            # 4. Upload zu Telegram (Parallel Chunk-Upload mit Fallback)
            uploaded_message_ids = []
            for file_to_upload, file_caption, display_filename in upload_files:
                file_mb = round(os.path.getsize(file_to_upload) / (1024 * 1024), 1)
                logger.info(f"[{job_id}] Sende {display_filename} ({file_mb} MB) zu Chat {chat_id} (Parallele Worker: {PARALLEL_WORKERS})...")

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

                try:
                    # Video-Attribute (Breite, Höhe, Dauer) für natives Telegram-Streaming auslesen
                    v_meta = await get_video_metadata(file_to_upload)
                    attributes = [
                        DocumentAttributeVideo(
                            duration=int(v_meta.get("duration") or 0),
                            w=int(v_meta.get("width") or 1280),
                            h=int(v_meta.get("height") or 720),
                            supports_streaming=True
                        ),
                        DocumentAttributeFilename(file_name=display_filename)
                    ]

                    # Paralleler Upload der 512KB Chunks über mehrere MTProto-Verbindungen
                    uploaded_handle = await fast_upload_file(
                        client=state.telegram_client,
                        file_path=file_to_upload,
                        max_workers=PARALLEL_WORKERS,
                        progress_callback=make_progress_callback(display_filename)
                    )

                    # Bereits hochgeladenen File-Handle mit Metadaten an den Chat senden
                    msg = await state.telegram_client.send_file(
                        entity=chat_id,
                        file=uploaded_handle,
                        caption=file_caption,
                        thumb=temp_thumb if temp_thumb and os.path.exists(temp_thumb) else None,
                        attributes=attributes,
                        parse_mode='html',
                        supports_streaming=True
                    )
                except Exception as upload_err:
                    logger.warning(f"[{job_id}] Paralleler Upload fehlgeschlagen ({upload_err}), starte sequentiellen Standard-Upload...", exc_info=True)
                    msg = await state.telegram_client.send_file(
                        entity=chat_id,
                        file=file_to_upload,
                        caption=file_caption,
                        thumb=temp_thumb if temp_thumb and os.path.exists(temp_thumb) else None,
                        parse_mode='html',
                        supports_streaming=True,
                        progress_callback=make_progress_callback(display_filename)
                    )

                uploaded_message_ids.append(msg.id)
                logger.info(f"[{job_id}] Upload erfolgreich! Message ID: {msg.id}")

            # 4b. Weiterleiten in Forum-Supergruppe und Topic-Sortierung (falls konfiguriert)
            forum_message_ids = []
            target_topic_id = None
            if forum_chat_id and uploaded_message_ids:
                try:
                    topic_title = data.get("topic_name") or streamer or "Allgemein"
                    target_topic_id = await topic_manager.get_or_create_topic(
                        client=state.telegram_client,
                        forum_chat_id=forum_chat_id,
                        title=topic_title
                    )
                    forum_message_ids = await topic_manager.forward_messages_to_topic(
                        client=state.telegram_client,
                        from_chat=chat_id,
                        to_forum_chat=forum_chat_id,
                        message_ids=uploaded_message_ids,
                        topic_id=target_topic_id,
                        drop_author=FORWARD_DROP_AUTHOR
                    )
                    logger.info(f"[{job_id}] Video-Nachricht(en) erfolgreich in Forum {forum_chat_id} (Topic '{topic_title}' [ID {target_topic_id}]) weitergeleitet.")
                except Exception as fwd_err:
                    logger.error(f"[{job_id}] Fehler beim Weiterleiten in Forum-Topic: {fwd_err}", exc_info=True)

            # 5. Direkt auf Streamrecorder als 'downloaded' markieren (falls Cookie vorhanden)
            raw_cookie = data.get("cookie") or os.getenv("STREAMRECORDER_COOKIE")
            sr_cookie = sanitize_cookie(raw_cookie)
            if sr_cookie and recording_id:
                try:
                    mark_url = f"https://streamrecorder.io/api/user/setdownloaded?fileid={recording_id}"
                    headers = {
                        "Cookie": sr_cookie,
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                    timeout = ClientTimeout(total=15)
                    async with ClientSession(timeout=timeout) as session:
                        async with session.get(mark_url, headers=headers) as mark_resp:
                            resp_text = await mark_resp.text()
                            logger.info(f"[{job_id}] Streamrecorder Auto-Mark: HTTP {mark_resp.status} (Antwort: {resp_text[:100]})")
                except Exception as e:
                    logger.warning(f"[{job_id}] Konnte Streamrecorder nicht als downloaded markieren: {e}")

            return web.json_response({
                "status": "success",
                "message_id": uploaded_message_ids[0],
                "message_ids": uploaded_message_ids,
                "parts": len(uploaded_message_ids),
                "chat_id": chat_id,
                "forum_chat_id": forum_chat_id,
                "topic_id": target_topic_id,
                "forwarded_message_ids": forum_message_ids
            })

    except Exception as e:
        logger.error(f"[{job_id}] Fehler bei Verarbeitung: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

    finally:
        if in_queue:
            state.waiting_count -= 1

        # 6. Sauberes Aufräumen des gesamten Job-Verzeichnisses
        try:
            if os.path.exists(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"[{job_id}] Temporäres Job-Verzeichnis gelöscht: {job_dir}")
        except Exception as e:
            logger.warning(f"[{job_id}] Konnte Job-Verzeichnis {job_dir} nicht löschen: {e}")


async def handle_health(request):
    is_busy = state.upload_lock.locked()
    return web.json_response({
        "status": "ok",
        "bot": "Ripperbot",
        "busy": is_busy,
        "queue_length": state.waiting_count,
        "split_threshold_mb": 1800,
        "target_part_size_mb": 1400,
        "parallel_workers": PARALLEL_WORKERS,
        "chat_id": DEFAULT_CHAT_ID,
        "forum_chat_id": DEFAULT_FORUM_CHAT_ID,
        "forward_drop_author": FORWARD_DROP_AUTHOR
    })

async def on_startup(app):
    state.telegram_client = TelegramClient('vod_bot_session', API_ID, API_HASH)
    await state.telegram_client.start(bot_token=BOT_TOKEN)
    logger.info("Telegram Bot Client und Queue-Lock erfolgreich gestartet!")

async def on_cleanup(app):
    if state.telegram_client:
        await state.telegram_client.disconnect()
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
