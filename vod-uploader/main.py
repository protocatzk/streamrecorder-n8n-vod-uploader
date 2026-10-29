import os
import re
import glob
import math
import shutil
import asyncio
import logging
import uuid
import time
import secrets
import json
import html
import collections
from datetime import datetime
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout, ClientError, ClientPayloadError
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from dotenv import load_dotenv, find_dotenv
from fast_uploader import fast_upload_file, get_video_metadata, parse_duration_to_seconds
from topic_manager import topic_manager
from rss_archiver import RssArchiver, RssItem, LiveStream, is_live_error
from dashboard_templates import LOGIN_HTML, DASHBOARD_HTML, TOPICS_HTML

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
PARALLEL_WORKERS = int(os.getenv('PARALLEL_UPLOAD_WORKERS', '3'))
FFMPEG_THREADS = int(os.getenv('FFMPEG_THREADS', '2'))
ALLOWED_DASHBOARD_USERS = os.getenv('ALLOWED_DASHBOARD_USERS', '@Ripperchieff,@x42067')
DOWNLOAD_INACTIVITY_TIMEOUT = int(os.getenv('DOWNLOAD_INACTIVITY_TIMEOUT', '120'))
DOWNLOAD_CHUNK_SIZE = max(64 * 1024, int(os.getenv('DOWNLOAD_CHUNK_SIZE', str(1024 * 1024))))

# --- rss.app Archiv ---
RSS_ENABLED = os.getenv('RSS_ENABLED', 'true').lower() in ('true', '1', 'yes')
RSS_OPML_FILE = os.getenv('RSS_OPML_FILE', 'rss-app-opml.xml')
RSS_FEED_URLS = [u.strip() for u in os.getenv('RSS_FEED_URLS', '').replace('\n', ',').split(',') if u.strip()]
RSS_FEED_TITLES = [t.strip() for t in os.getenv('RSS_FEED_TITLES', '').split(',') if t.strip()]
RSS_STATE_FILE = os.getenv('RSS_STATE_FILE', 'rss_data/rss_state.json')
RSS_POLL_INTERVAL = int(os.getenv('RSS_POLL_INTERVAL_SECONDS', '900'))
RSS_INITIAL_BACKFILL = os.getenv('RSS_INITIAL_BACKFILL', 'false').lower() in ('true', '1', 'yes')
RSS_MAX_ITEM_AGE_HOURS = int(os.getenv('RSS_MAX_ITEM_AGE_HOURS', '48'))
RSS_MAX_ITEMS_PER_POLL = int(os.getenv('RSS_MAX_ITEMS_PER_POLL', '10'))
RSS_RETENTION_DAYS = int(os.getenv('RSS_STATE_RETENTION_DAYS', '90'))
RSS_ALLOW_LIVE = os.getenv('RSS_ALLOW_LIVE', 'false').lower() in ('true', '1', 'yes')
RSS_TOPIC_PER_FEED = os.getenv('RSS_TOPIC_PER_FEED', 'true').lower() in ('true', '1', 'yes')
RSS_ARCHIVE_CHAT_ID = os.getenv('RSS_ARCHIVE_CHAT_ID') or None
RSS_ARCHIVE_FORUM_CHAT_ID = os.getenv('RSS_ARCHIVE_FORUM_CHAT_ID') or None
RSS_MAX_RETRIES = int(os.getenv('RSS_MAX_RETRIES', '0'))
RSS_RETRY_BASE_SECONDS = int(os.getenv('RSS_RETRY_BASE_SECONDS', '900'))
RSS_RETRY_MAX_DELAY_SECONDS = int(os.getenv('RSS_RETRY_MAX_DELAY_SECONDS', '21600'))
RSS_LIVE_RECHECK_SECONDS = int(os.getenv('RSS_LIVE_RECHECK_SECONDS', '900'))
YTDLP_COOKIES_FILE = os.getenv('YTDLP_COOKIES_FILE') or None
YTDLP_CONCURRENT_FRAGMENTS = int(os.getenv('YTDLP_CONCURRENT_FRAGMENTS', '4'))
YTDLP_RETRIES = int(os.getenv('YTDLP_RETRIES', '10'))
YTDLP_HTTP_CHUNK_SIZE = int(os.getenv('YTDLP_HTTP_CHUNK_SIZE', str(10 * 1024 * 1024)))
YTDLP_FORMAT = os.getenv('YTDLP_FORMAT', '').strip() or None

# --- n8n Workflows (Dashboard-Buttons) ---
def parse_n8n_webhooks(raw: str) -> dict[str, str]:
    """Liest 'name=url,name=url' in ein Dict name -> Webhook-URL."""
    hooks = {}
    for entry in (raw or '').replace('\n', ',').split(','):
        entry = entry.strip()
        if not entry or '=' not in entry:
            continue
        name, url = entry.split('=', 1)
        name, url = name.strip(), url.strip()
        if name and url:
            hooks[name] = url
    return hooks

N8N_WEBHOOKS = parse_n8n_webhooks(os.getenv('N8N_WEBHOOKS', ''))
N8N_WEBHOOK_TIMEOUT = max(1, int(os.getenv('N8N_WEBHOOK_TIMEOUT', '10')))
N8N_TRIGGER_COOLDOWN = max(0, int(os.getenv('N8N_TRIGGER_COOLDOWN', '10')))

logger.info(f"Konfiguration geladen (API_ID: {API_ID}, Default Chat: {DEFAULT_CHAT_ID}, Forum Chat: {DEFAULT_FORUM_CHAT_ID}, Drop Author: {FORWARD_DROP_AUTHOR}, Split-Schwelle: 1.8 GB, Zielgröße: 1.4 GB, Parallele Upload-Worker: {PARALLEL_WORKERS}, FFmpeg-Threads: {FFMPEG_THREADS}, Erlaubte Dashboard-User: {ALLOWED_DASHBOARD_USERS}, Inaktivitäts-Timeout: {DOWNLOAD_INACTIVITY_TIMEOUT}s)")

PLATFORM_ICONS = {
    'tiktok': '📱 TikTok',
    'twitch': '🟣 Twitch',
    'kick': '🟢 Kick',
    'youtube': '🔴 YouTube',
    'x': '✖️ X (Twitter)',
    'twitter': '✖️ X (Twitter)',
    'instagram': '📸 Instagram',
    'facebook': '📘 Facebook',
    'vimeo': '🎬 Vimeo',
    'reddit': '👽 Reddit',
    'streamable': '🎞 Streamable',
    'odysee': '▶️ Odysee',
    'rumble': '🟩 Rumble',
    'bitchute': '📼 BitChute',
    'dailymotion': '📺 Dailymotion',
    'vk': '🇷🇺 VK',
    'bilibili': '📺 Bilibili',
}

def escape_html(value) -> str:
    return html.escape(str(value or ''), quote=False)

def format_duration_seconds(seconds) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "N/A"
    if total <= 0:
        return "N/A"
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

class BotState:
    def __init__(self):
        self.upload_lock = asyncio.Lock()
        self.waiting_count = 0
        self.telegram_client: TelegramClient | None = None
        self.bot_username: str = ""
        self.active_job: dict | None = None
        self.waiting_queue: list[dict] = []
        self.history: collections.deque = collections.deque(maxlen=30)
        self.log_buffer: collections.deque = collections.deque(maxlen=60)
        self.pending_auth: dict = {}
        self.active_sessions: dict = {}
        self.sse_queues: set[asyncio.Queue] = set()
        self.n8n_last_trigger: dict[str, float] = {}

state = BotState()

class MemoryLogHandler(logging.Handler):
    def __init__(self, buffer: collections.deque):
        super().__init__()
        self.buffer = buffer

    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append({
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": msg
            })
        except Exception:
            pass

mem_handler = MemoryLogHandler(state.log_buffer)
mem_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(mem_handler)

async def download_file(
    url: str,
    output_path: str,
    progress_callback=None,
    inactivity_timeout: int = DOWNLOAD_INACTIVITY_TIMEOUT,
    chunk_size: int = DOWNLOAD_CHUNK_SIZE,
):
    chunk_size = max(64 * 1024, int(chunk_size))
    logger.info(
        f"Starte Download von: {url[:80]}... nach {output_path} "
        f"(Inaktivitäts-Timeout: {inactivity_timeout}s, Chunk: {chunk_size // 1024} KB)"
    )
    timeout = ClientTimeout(total=None, sock_read=inactivity_timeout, sock_connect=30)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive"
    }

    try:
        async with ClientSession(timeout=timeout, read_bufsize=chunk_size) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Download fehlgeschlagen mit HTTP {response.status}")

                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                last_logged_mb = 0
                with open(output_path, 'wb') as f:
                    while True:
                        try:
                            chunk = await asyncio.wait_for(response.content.read(chunk_size), timeout=float(inactivity_timeout))
                        except (asyncio.TimeoutError, TimeoutError):
                            raise asyncio.TimeoutError(f"Inaktivitäts-Timeout: Seit {inactivity_timeout} Sekunden wurden keine Daten empfangen.")

                        if not chunk:
                            break

                        await asyncio.to_thread(f.write, chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)
                        mb = downloaded // (100 * 1024 * 1024)
                        if mb > last_logged_mb:
                            last_logged_mb = mb
                            pct = f" ({round(downloaded / total_size * 100)}%)" if total_size else ""
                            logger.info(f"Download Fortschritt: {round(downloaded / (1024*1024))} MB{pct}")

                if total_size and downloaded < total_size:
                    raise ClientPayloadError(
                        f"Unvollständige Übertragung: {downloaded} von {total_size} Bytes empfangen."
                    )

                logger.info(f"Download fertig: {downloaded} Bytes heruntergeladen ({round(downloaded/1024/1024, 1)} MB).")

    except (ClientError, asyncio.TimeoutError, TimeoutError, OSError) as e:
        logger.error(f"Download fehlgeschlagen ({type(e).__name__}: {e})")
        raise


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
        "-threads", str(FFMPEG_THREADS),
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

async def process_job(data: dict) -> tuple[dict, int]:
    """Verarbeitet einen Download-/Upload-Job.

    Wird sowohl von ``/upload`` (n8n) als auch vom RSS-Archiv aufgerufen und
    serialisiert alle Uploads über ``state.upload_lock``.
    """
    download_url = data.get("download_url")
    if not download_url:
        return {"error": "Missing download_url"}, 400

    recording_id = str(data.get("recording_id", ""))
    job_id = recording_id or str(uuid.uuid4())[:8]
    streamer = data.get("streamer", "Unbekannt")
    title = data.get("title", "Livestream Recording")
    source = str(data.get("source") or "streamrecorder")
    use_ytdlp = bool(data.get("use_ytdlp"))
    source_url = data.get("source_url")

    job_info = {
        "job_id": job_id,
        "streamer": streamer,
        "title": title,
        "source": source,
        "queued_at": datetime.now().strftime("%H:%M:%S")
    }
    state.waiting_queue.append(job_info)
    state.waiting_count += 1
    in_queue = True
    logger.info(f"[{job_id}] Request eingereiht ({streamer} - '{title}', Quelle: {source}). Wartende Jobs: {state.waiting_count}.")

    job_dir = f"/tmp/job_{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    temp_video = os.path.join(job_dir, f"stream_{job_id}.mp4")
    temp_thumb = os.path.join(job_dir, f"thumb_{job_id}.jpg") if data.get("thumbnail_url") else None
    platform = str(data.get("platform") or "").lower()
    actual_size_mb = 0
    uploaded_message_ids = []

    try:
        async with state.upload_lock:
            in_queue = False
            state.waiting_count -= 1
            if job_info in state.waiting_queue:
                state.waiting_queue.remove(job_info)

            logger.info(f"[{job_id}] Bearbeitung gestartet! (Verbleibend in Queue: {state.waiting_count})")

            raw_chat_id = data.get("chat_id", DEFAULT_CHAT_ID)
            try:
                chat_id = int(raw_chat_id)
            except (ValueError, TypeError):
                chat_id = raw_chat_id

            raw_forum_chat_id = data.get("forum_chat_id", DEFAULT_FORUM_CHAT_ID)
            forum_chat_id = None
            if raw_forum_chat_id:
                try:
                    forum_chat_id = int(raw_forum_chat_id)
                except (ValueError, TypeError):
                    forum_chat_id = raw_forum_chat_id

            duration = data.get("duration", "N/A")
            filesize_mb = data.get("filesize_mb", "N/A")
            thumbnail_url = data.get("thumbnail_url")
            category = data.get("category", "")
            max_viewers = data.get("max_viewers")
            avg_viewers = data.get("avg_viewers")
            deletion_time = data.get("deletion_time", "")
            recorded_at = data.get("recorded_at", "")
            formatted_date = format_recorded_at(recorded_at)
            download_label = "Download aus RSS-Feed" if source == "rss" else "Download von Streamrecorder"

            state.active_job = {
                "job_id": job_id,
                "streamer": streamer,
                "title": title,
                "platform": platform,
                "source": source,
                "stage": "downloading",
                "stage_label": download_label,
                "pct": 0,
                "bytes_done": 0,
                "bytes_total": 0,
                "current_part": 0,
                "total_parts": 0,
                "part_name": "",
                "speed_mbps": 0.0,
                "eta_seconds": None,
                "started_at": datetime.now().strftime("%H:%M:%S")
            }

            # 1. Thumbnail vorab laden
            if thumbnail_url:
                try:
                    await download_file(thumbnail_url, temp_thumb, inactivity_timeout=30)
                    logger.info(f"[{job_id}] Thumbnail erfolgreich geladen.")
                except Exception as e:
                    logger.warning(f"[{job_id}] Thumbnail konnte nicht geladen werden, fahre ohne fort: {e}")
                    temp_thumb = None

            # 2. Video herunterladen
            last_dl_report_time = 0.0
            def dl_progress(done, total):
                nonlocal last_dl_report_time
                now = time.time()
                if now - last_dl_report_time < 0.5 and done < total:
                    return
                last_dl_report_time = now
                if state.active_job:
                    state.active_job['bytes_done'] = done
                    state.active_job['bytes_total'] = total
                    state.active_job['pct'] = int(done / total * 100) if total else 0
                    state.active_job['stage'] = 'downloading'
                    state.active_job['stage_label'] = download_label

            try:
                if use_ytdlp:
                    if state.active_job:
                        state.active_job['stage_label'] = "Video-Analyse (yt-dlp)"
                    temp_video = await rss_archiver.download_video(
                        download_url,
                        os.path.join(job_dir, f"stream_{job_id}"),
                        progress_callback=dl_progress
                    )
                    logger.info(f"[{job_id}] yt-dlp-Download abgeschlossen: {os.path.basename(temp_video)}")
                else:
                    await download_file(download_url, temp_video, progress_callback=dl_progress, inactivity_timeout=DOWNLOAD_INACTIVITY_TIMEOUT)
            except LiveStream as live_err:
                logger.info(f"[{job_id}] {live_err}. Item bleibt für einen späteren Versuch vorgemerkt.")
                if state.active_job and state.active_job.get("job_id") == job_id:
                    state.active_job['stage'] = 'waiting'
                    state.active_job['stage_label'] = str(live_err)
                return {
                    "status": "live",
                    "job_id": job_id,
                    "message": str(live_err)
                }, 200
            except Exception as dl_err:
                if use_ytdlp and is_live_error(dl_err):
                    logger.info(f"[{job_id}] Live/Premiere erkannt ({dl_err}). Item bleibt für einen späteren Versuch vorgemerkt.")
                    if state.active_job and state.active_job.get("job_id") == job_id:
                        state.active_job['stage'] = 'waiting'
                        state.active_job['stage_label'] = "Wartet auf Stream-Ende"
                    return {
                        "status": "live",
                        "job_id": job_id,
                        "message": str(dl_err)
                    }, 200
                logger.warning(f"[{job_id}] Download abgebrochen oder fehlgeschlagen ({dl_err}). Video wird übersprungen.")
                if state.active_job and state.active_job.get("job_id") == job_id:
                    state.active_job['stage'] = 'skipped'
                    is_timeout = isinstance(dl_err, (asyncio.TimeoutError, TimeoutError)) or 'Inaktivitäts-Timeout' in str(dl_err)
                    state.active_job['stage_label'] = f"Übersprungen ({DOWNLOAD_INACTIVITY_TIMEOUT}s Timeout)" if is_timeout else "Übersprungen (Download fehlgeschlagen)"
                return {
                    "status": "skipped",
                    "job_id": job_id,
                    "message": f"Download fehlgeschlagen ({dl_err}), Video übersprungen."
                }, 200

            if not os.path.exists(temp_video):
                return {"status": "skipped", "job_id": job_id, "message": "Download-Datei fehlt."}, 200

            actual_size = os.path.getsize(temp_video)
            actual_size_mb = round(actual_size / (1024 * 1024), 1)
            logger.info(f"[{job_id}] Download abgeschlossen. Tatsächliche Größe: {actual_size_mb} MB")

            platform_label = PLATFORM_ICONS.get(platform, f"🌐 {platform.capitalize() if platform else 'Stream'}")
            clean_streamer = "".join(c for c in streamer if c.isalnum() or c in ('_', '-')).strip() or "stream"
            heading = "Neues RSS-Video" if source == "rss" else "Neues Stream-Recording"
            person_label = "Kanal" if source == "rss" else "Streamer"
            source_line = None
            if source_url:
                safe_source = html.escape(str(source_url), quote=True)
                source_line = f'🔗 <b>Quelle:</b> <a href="{safe_source}">Original</a>'
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
                    f"🎥 <b>{heading} (Teil 1/{total_parts})</b>\n",
                    f"👤 <b>{person_label}:</b> {escape_html(streamer)}",
                    f"📌 <b>Titel:</b> {escape_html(title)}"
                ]
                if category:
                    caption_lines.append(f"🎮 <b>Kategorie:</b> {escape_html(category)} | {platform_label}")
                else:
                    caption_lines.append(f"📡 <b>Plattform:</b> {platform_label}")

                caption_lines.append("")
                if formatted_date:
                    caption_lines.append(f"📅 <b>Datum:</b> {escape_html(formatted_date)}")
                caption_lines.append(f"⏱ <b>Gesamtdauer:</b> {escape_html(duration)}")
                caption_lines.append(f"💾 <b>Gesamtgröße:</b> {actual_size_mb} MB ({total_parts} Teile)")
                caption_lines.append(f"🆔 <b>ID:</b> <code>{escape_html(recording_id)}</code>")
                if source_line:
                    caption_lines.append(source_line)
                main_caption = "\n".join(caption_lines)
                display_filename_1 = f"{clean_streamer}_{job_id}_part01.mp4"
                upload_files.append((split_parts[0], main_caption, display_filename_1))

                # Teil 2..N nummeriert
                for idx, part_path in enumerate(split_parts[1:], start=2):
                    sub_caption_lines = [
                        f"🎥 <b>{heading} (Teil {idx}/{total_parts})</b>\n",
                        f"👤 <b>{person_label}:</b> {escape_html(streamer)}",
                        f"📌 <b>Titel:</b> {escape_html(title)}"
                    ]
                    if formatted_date:
                        sub_caption_lines.append(f"📅 <b>Datum:</b> {escape_html(formatted_date)}")
                    sub_caption_lines.append(f"🆔 <b>ID:</b> <code>{escape_html(recording_id)}</code>")
                    if source_line:
                        sub_caption_lines.append(source_line)
                    sub_caption = "\n".join(sub_caption_lines)
                    display_filename_n = f"{clean_streamer}_{job_id}_part{idx:02d}.mp4"
                    upload_files.append((part_path, sub_caption, display_filename_n))
            else:
                caption_lines = [
                    f"🎥 <b>{heading}</b>\n",
                    f"👤 <b>{person_label}:</b> {escape_html(streamer)}",
                    f"📌 <b>Titel:</b> {escape_html(title)}"
                ]
                if category:
                    caption_lines.append(f"🎮 <b>Kategorie:</b> {escape_html(category)} | {platform_label}")
                else:
                    caption_lines.append(f"📡 <b>Plattform:</b> {platform_label}")

                caption_lines.append("")
                if formatted_date:
                    caption_lines.append(f"📅 <b>Datum:</b> {escape_html(formatted_date)}")
                caption_lines.append(f"⏱ <b>Dauer:</b> {escape_html(duration)}")
                caption_lines.append(f"💾 <b>Größe:</b> {actual_size_mb} MB")
                caption_lines.append(f"🆔 <b>ID:</b> <code>{escape_html(recording_id)}</code>")
                if source_line:
                    caption_lines.append(source_line)
                caption = "\n".join(caption_lines)
                display_filename_single = f"{clean_streamer}_{job_id}.mp4"
                upload_files.append((temp_video, caption, display_filename_single))

            # 4. Upload zu Telegram (Parallel Chunk-Upload mit Fallback)
            uploaded_message_ids = []
            total_upload_files = len(upload_files)
            for part_idx, (file_to_upload, file_caption, display_filename) in enumerate(upload_files, start=1):
                file_mb = round(os.path.getsize(file_to_upload) / (1024 * 1024), 1)
                logger.info(f"[{job_id}] Sende {display_filename} ({file_mb} MB) zu Chat {chat_id} (Parallele Worker: {PARALLEL_WORKERS})...")

                if state.active_job:
                    state.active_job['stage'] = 'uploading'
                    state.active_job['stage_label'] = f"Upload Teil {part_idx}/{total_upload_files}"
                    state.active_job['current_part'] = part_idx
                    state.active_job['total_parts'] = total_upload_files
                    state.active_job['part_name'] = display_filename
                    state.active_job['pct'] = 0

                last_reported_pct = -1
                last_calc_time = time.time()
                last_calc_bytes = 0
                last_ui_update_time = 0.0

                def make_progress_callback(f_name, p_idx, p_total):
                    nonlocal last_reported_pct, last_calc_time, last_calc_bytes, last_ui_update_time
                    def callback(current, total):
                        nonlocal last_reported_pct, last_calc_time, last_calc_bytes, last_ui_update_time
                        pct = int(current / total * 100) if total else 0
                        now = time.time()
                        time_diff = now - last_calc_time
                        if time_diff >= 1.0:
                            bytes_diff = current - last_calc_bytes
                            speed_mbps = (bytes_diff / (1024 * 1024)) / time_diff if time_diff > 0 else 0.0
                            eta_sec = (total - current) / (speed_mbps * 1024 * 1024) if speed_mbps > 0 and total > current else None
                            last_calc_time = now
                            last_calc_bytes = current

                            if state.active_job:
                                state.active_job['speed_mbps'] = speed_mbps
                                state.active_job['eta_seconds'] = eta_sec

                        if now - last_ui_update_time >= 0.5 or current >= total:
                            last_ui_update_time = now
                            if state.active_job:
                                state.active_job['bytes_done'] = current
                                state.active_job['bytes_total'] = total
                                state.active_job['pct'] = pct
                                state.active_job['stage'] = 'uploading'
                                state.active_job['stage_label'] = f"Upload Teil {p_idx}/{p_total}"

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
                        progress_callback=make_progress_callback(display_filename, part_idx, total_upload_files)
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
                        progress_callback=make_progress_callback(display_filename, part_idx, total_upload_files)
                    )

                uploaded_message_ids.append(msg.id)
                logger.info(f"[{job_id}] Upload erfolgreich! Message ID: {msg.id}")

            # 4b. Weiterleiten in Forum-Supergruppe und Topic-Sortierung (falls konfiguriert)
            forum_message_ids = []
            target_topic_id = None
            if forum_chat_id and uploaded_message_ids:
                try:
                    topic_title = data.get("topic_name") or streamer or "Allgemein"
                    if state.active_job:
                        state.active_job['stage'] = 'forwarding'
                        state.active_job['stage_label'] = f"Weiterleitung in Topic '{topic_title}'"

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
            if source != "rss" and sr_cookie and recording_id:
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

            if state.active_job:
                state.history.appendleft({
                    "job_id": job_id,
                    "streamer": streamer,
                    "title": title,
                    "platform": platform,
                    "source": source,
                    "parts": len(uploaded_message_ids),
                    "total_size_mb": actual_size_mb,
                    "topic_id": target_topic_id,
                    "topic_name": topic_title if 'topic_title' in locals() else streamer,
                    "status": "success",
                    "finished_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                })
                state.active_job = None

            return {
                "status": "success",
                "message_id": uploaded_message_ids[0],
                "message_ids": uploaded_message_ids,
                "parts": len(uploaded_message_ids),
                "chat_id": chat_id,
                "forum_chat_id": forum_chat_id,
                "topic_id": target_topic_id,
                "forwarded_message_ids": forum_message_ids
            }, 200

    except Exception as e:
        logger.error(f"[{job_id}] Fehler bei Verarbeitung: {e}", exc_info=True)
        if state.active_job:
            state.history.appendleft({
                "job_id": job_id,
                "streamer": streamer,
                "title": title,
                "platform": platform,
                "source": source,
                "parts": len(uploaded_message_ids),
                "total_size_mb": actual_size_mb,
                "topic_id": None,
                "topic_name": None,
                "status": "failed",
                "error": str(e),
                "finished_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            })
            state.active_job = None
        return {"error": str(e)}, 500

    finally:
        if in_queue:
            state.waiting_count -= 1
        if 'job_info' in locals() and job_info in state.waiting_queue:
            state.waiting_queue.remove(job_info)

        # 6. Sauberes Aufräumen des gesamten Job-Verzeichnisses
        try:
            if os.path.exists(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"[{job_id}] Temporäres Job-Verzeichnis gelöscht: {job_dir}")
        except Exception as e:
            logger.warning(f"[{job_id}] Konnte Job-Verzeichnis {job_dir} nicht löschen: {e}")


async def handle_upload(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    payload, status = await process_job(data)
    return web.json_response(payload, status=status)


async def archive_rss_item(item: RssItem) -> dict:
    """Baut aus einem Feed-Item einen Job fuer die bestehende Upload-Pipeline."""
    duration = format_duration_seconds(item.duration) if item.duration else "N/A"
    job_data = {
        "download_url": item.url,
        "use_ytdlp": True,
        "source": "rss",
        "source_url": item.url,
        "recording_id": item.recording_id,
        "streamer": item.channel,
        "title": item.title,
        "thumbnail_url": item.thumbnail,
        "platform": item.platform,
        "recorded_at": item.published_iso,
        "duration": duration,
        "chat_id": RSS_ARCHIVE_CHAT_ID or DEFAULT_CHAT_ID,
        "forum_chat_id": RSS_ARCHIVE_FORUM_CHAT_ID or DEFAULT_FORUM_CHAT_ID,
        "topic_name": item.channel if RSS_TOPIC_PER_FEED else None,
    }
    payload, status = await process_job(job_data)
    if status >= 400:
        raise RuntimeError(payload.get("error") or f"HTTP {status}")
    return payload


rss_archiver = RssArchiver(
    on_item=archive_rss_item,
    state_file=RSS_STATE_FILE,
    opml_file=RSS_OPML_FILE or None,
    feed_urls=RSS_FEED_URLS,
    feed_titles=RSS_FEED_TITLES,
    interval=RSS_POLL_INTERVAL,
    initial_backfill=RSS_INITIAL_BACKFILL,
    max_item_age_hours=RSS_MAX_ITEM_AGE_HOURS,
    max_items_per_poll=RSS_MAX_ITEMS_PER_POLL,
    max_retries=RSS_MAX_RETRIES,
    retry_base_seconds=RSS_RETRY_BASE_SECONDS,
    retry_max_delay_seconds=RSS_RETRY_MAX_DELAY_SECONDS,
    live_recheck_seconds=RSS_LIVE_RECHECK_SECONDS,
    retention_days=RSS_RETENTION_DAYS,
    allow_live=RSS_ALLOW_LIVE,
    cookies_file=YTDLP_COOKIES_FILE,
    enabled=RSS_ENABLED,
    ytdlp_concurrent_fragments=YTDLP_CONCURRENT_FRAGMENTS,
    ytdlp_retries=YTDLP_RETRIES,
    ytdlp_http_chunk_size=YTDLP_HTTP_CHUNK_SIZE,
    ytdlp_format=YTDLP_FORMAT,
)


async def handle_rss_status(request):
    return web.json_response(rss_archiver.status())


async def handle_rss_check(request):
    if not RSS_ENABLED:
        return web.json_response({"status": "disabled"}, status=503)
    started = rss_archiver.trigger()
    return web.json_response(
        {"status": "started" if started else "busy"},
        status=202 if started else 409,
    )


async def handle_rss_backfill(request):
    if not RSS_ENABLED:
        return web.json_response({"status": "disabled"}, status=503)
    try:
        limit = int(request.query.get("limit", "10"))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))
    started = rss_archiver.trigger_backfill(limit)
    return web.json_response(
        {"status": "started" if started else "busy", "limit": limit},
        status=202 if started else 409,
    )


async def handle_n8n_run(request):
    """Startet einen (oder alle) n8n-Workflow(s) ueber deren Webhook-Trigger."""
    if not get_authed_session(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not N8N_WEBHOOKS:
        return web.json_response({"status": "disabled"}, status=503)

    name = (request.query.get("name") or "").strip()
    if name and name not in N8N_WEBHOOKS:
        return web.json_response(
            {"error": "Unknown workflow", "available": sorted(N8N_WEBHOOKS)},
            status=404,
        )

    targets = [name] if name else list(N8N_WEBHOOKS)
    now = time.time()
    results = []
    timeout = ClientTimeout(total=N8N_WEBHOOK_TIMEOUT)

    async with ClientSession(timeout=timeout) as session:
        for target in targets:
            last = state.n8n_last_trigger.get(target, 0.0)
            if N8N_TRIGGER_COOLDOWN and (now - last) < N8N_TRIGGER_COOLDOWN:
                results.append({"name": target, "ok": False, "status": "cooldown"})
                continue
            state.n8n_last_trigger[target] = now
            try:
                async with session.post(N8N_WEBHOOKS[target]) as resp:
                    body = await resp.text()
                    ok = resp.status < 400
                    logger.info(f"n8n-Workflow '{target}' gestartet (HTTP {resp.status})")
                    results.append({
                        "name": target,
                        "ok": ok,
                        "http_status": resp.status,
                        "response": body[:200],
                    })
            except asyncio.TimeoutError:
                logger.warning(f"n8n-Workflow '{target}': Timeout nach {N8N_WEBHOOK_TIMEOUT}s")
                results.append({"name": target, "ok": False, "status": "timeout"})
            except Exception as exc:
                logger.warning(f"n8n-Workflow '{target}' fehlgeschlagen: {exc}")
                results.append({"name": target, "ok": False, "status": "error"})

    started = [r for r in results if r["ok"]]
    if not started:
        status = 429 if all(r.get("status") == "cooldown" for r in results) else 502
        return web.json_response({"status": "failed", "workflows": results}, status=status)

    return web.json_response(
        {"status": "started", "workflows": results},
        status=202,
    )


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
        "forward_drop_author": FORWARD_DROP_AUTHOR,
        "rss": rss_archiver.summary()
    })

# --- Dashboard & Telegram Authentication Handlers ---

def get_authed_session(request):
    """Gibt die aktive Dashboard-Session zurück oder None."""
    session_id = request.cookies.get("vod_session")
    if not session_id:
        return None
    session = state.active_sessions.get(session_id)
    if not session:
        return None
    if time.time() > session.get("expires_at", 0):
        state.active_sessions.pop(session_id, None)
        return None
    return session


def count_mapped_topics() -> int:
    """Anzahl eindeutiger Topic-IDs über alle Chats im Cache."""
    topic_ids = set()
    for chat_topics in topic_manager.cache.values():
        if isinstance(chat_topics, dict):
            topic_ids.update(
                tid for tid in chat_topics.values()
                if isinstance(tid, int) and not isinstance(tid, bool)
            )
    return len(topic_ids)


# --- Topic-Verwaltung ---

def _json_error(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


def topic_chat_ids() -> list[str]:
    chats = [
        str(key) for key, value in topic_manager.cache.items()
        if isinstance(value, dict)
    ]
    configured = str(DEFAULT_FORUM_CHAT_ID).strip() if DEFAULT_FORUM_CHAT_ID else ""
    if configured and configured not in chats:
        chats.insert(0, configured)
    return chats


def resolve_topic_chat(raw=None) -> str:
    configured = str(DEFAULT_FORUM_CHAT_ID).strip() if DEFAULT_FORUM_CHAT_ID else ""
    candidate = str(raw).strip() if raw not in (None, "") else ""
    chats = topic_chat_ids()
    if candidate:
        if candidate in chats or candidate == configured:
            return candidate
        raise ValueError("Unbekannter Chat.")
    if configured:
        return configured
    if chats:
        return chats[0]
    raise ValueError("Kein Forum-Chat konfiguriert.")


def validate_topic_name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("Name darf nicht leer sein.")
    if len(name) > 128:
        raise ValueError("Name ist zu lang (max. 128 Zeichen).")
    return name


def find_alias(chat_id: str, name: str) -> str | None:
    """Sucht einen Alias case-insensitiv (wie das Smart-Matching des Bots)."""
    target = str(name or "").strip().casefold()
    for alias in topic_manager.list_topics(chat_id):
        if alias.strip().casefold() == target:
            return alias
    return None


def parse_topic_id(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Topic-ID muss eine positive Ganzzahl sein.")
    if isinstance(value, int):
        topic_id = value
    else:
        text = str(value or "").strip()
        if not text.isdigit():
            raise ValueError("Topic-ID muss eine positive Ganzzahl sein.")
        topic_id = int(text)
    if topic_id <= 0:
        raise ValueError("Topic-ID muss eine positive Ganzzahl sein.")
    return topic_id


def choose_topic_display_name(aliases: list[str]) -> str:
    """Wählt einen möglichst lesbaren Alias als Anzeigenamen der Gruppe."""
    def score(alias: str) -> int:
        points = 0
        if not alias.startswith('@'):
            points += 2
        if not alias.startswith('_'):
            points += 1
        if not alias.isdigit():
            points += 2
        if ' ' in alias:
            points += 1
        if any(ch.isupper() for ch in alias):
            points += 1
        if '.' in alias:
            points -= 1
        return points

    return sorted(aliases, key=lambda a: (-score(a), len(a), a.lower()))[0]


def build_topics_payload(chat_id: str) -> dict:
    groups: dict[int, list[str]] = {}
    for alias, topic_id in topic_manager.list_topics(chat_id).items():
        groups.setdefault(topic_id, []).append(alias)

    topics = []
    for topic_id, aliases in groups.items():
        aliases = sorted(aliases, key=lambda a: a.lower())
        topics.append({
            "topic_id": topic_id,
            "name": choose_topic_display_name(aliases),
            "aliases": aliases,
            "link": f"https://t.me/RippersArchiv/{topic_id}",
        })
    topics.sort(key=lambda row: row["name"].lower())

    return {
        "chat_id": chat_id,
        "chats": topic_chat_ids(),
        "forum_chat_id": str(DEFAULT_FORUM_CHAT_ID).strip() if DEFAULT_FORUM_CHAT_ID else "",
        "topics": topics,
        "alias_count": sum(len(row["aliases"]) for row in topics),
    }


async def handle_topics_page(request):
    if not get_authed_session(request):
        raise web.HTTPFound('/voduploader')
    return web.Response(text=TOPICS_HTML, content_type='text/html')


async def handle_topics_list(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        chat_id = resolve_topic_chat(request.query.get('chat_id'))
    except ValueError as exc:
        return _json_error(str(exc))
    return web.json_response(build_topics_payload(chat_id))


async def handle_topic_create(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        data = await request.json()
    except Exception:
        return _json_error("Ungültige Anfrage.")
    if not isinstance(data, dict):
        return _json_error("JSON-Objekt erwartet.")

    try:
        chat_id = resolve_topic_chat(data.get('chat_id'))
        name = validate_topic_name(data.get('name'))
        create_raw = data.get('create')
        create_in_telegram = (
            create_raw is True or str(create_raw).strip().lower() in ('true', '1', 'yes')
        )

        existing_alias = find_alias(chat_id, name)
        existing_topic_id = (
            topic_manager.list_topics(chat_id).get(existing_alias)
            if existing_alias is not None else None
        )

        if create_in_telegram:
            if existing_alias is not None:
                return _json_error(
                    f"Der Name '{existing_alias}' existiert bereits "
                    f"(Topic {existing_topic_id}). Bitte einen anderen Namen wählen.",
                    409,
                )
            if not state.telegram_client:
                return _json_error("Telegram-Client ist noch nicht verbunden.", 503)
            topic_id = await topic_manager.create_topic(
                state.telegram_client, chat_id, name
            )
        else:
            topic_id = parse_topic_id(data.get('topic_id'))
            if existing_alias is not None and existing_topic_id != topic_id:
                return _json_error(
                    f"Der Name '{existing_alias}' ist bereits dem Topic "
                    f"{existing_topic_id} zugeordnet.",
                    409,
                )
            topic_manager.add_alias(chat_id, name, topic_id)
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        logger.error(f"Topic konnte nicht erstellt werden: {exc}", exc_info=True)
        return _json_error(f"Topic konnte nicht erstellt werden: {exc}", 502)

    logger.info(f"Topic-Verwaltung: '{name}' -> Topic {topic_id} hinzugefügt.")
    return web.json_response({"status": "ok", "topic_id": topic_id})


async def handle_topic_update(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        data = await request.json()
    except Exception:
        return _json_error("Ungültige Anfrage.")
    if not isinstance(data, dict):
        return _json_error("JSON-Objekt erwartet.")

    try:
        chat_id = resolve_topic_chat(data.get('chat_id'))
        old_topic_id = parse_topic_id(data.get('topic_id'))
        new_topic_id = parse_topic_id(data.get('new_topic_id'))
    except ValueError as exc:
        return _json_error(str(exc))

    existing_ids = set(topic_manager.list_topics(chat_id).values())
    if old_topic_id not in existing_ids:
        return _json_error("Topic nicht gefunden.", 404)
    if new_topic_id != old_topic_id and new_topic_id in existing_ids:
        return _json_error(
            f"Topic-ID {new_topic_id} existiert bereits. Bitte zuerst die andere Gruppe löschen.",
            409,
        )

    changed = topic_manager.remap_topic(chat_id, old_topic_id, new_topic_id)
    logger.info(
        f"Topic-Verwaltung: Topic {old_topic_id} -> {new_topic_id} "
        f"({changed} Alias(e) aktualisiert)."
    )
    return web.json_response({"status": "ok", "changed": changed})


async def handle_topic_delete(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        chat_id = resolve_topic_chat(request.query.get('chat_id'))
        topic_id = parse_topic_id(request.query.get('topic_id'))
    except ValueError as exc:
        return _json_error(str(exc))

    removed = topic_manager.delete_topic(chat_id, topic_id)
    if not removed:
        return _json_error("Topic nicht gefunden.", 404)
    logger.info(f"Topic-Verwaltung: Topic {topic_id} mit {removed} Alias(en) gelöscht.")
    return web.json_response({"status": "ok", "removed": removed})


async def handle_topic_alias_create(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        data = await request.json()
    except Exception:
        return _json_error("Ungültige Anfrage.")
    if not isinstance(data, dict):
        return _json_error("JSON-Objekt erwartet.")

    try:
        chat_id = resolve_topic_chat(data.get('chat_id'))
        name = validate_topic_name(data.get('name'))
        topic_id = parse_topic_id(data.get('topic_id'))
    except ValueError as exc:
        return _json_error(str(exc))

    existing_alias = find_alias(chat_id, name)
    existing = (
        topic_manager.list_topics(chat_id).get(existing_alias)
        if existing_alias is not None else None
    )
    if existing is not None and existing != topic_id:
        return _json_error(
            f"Der Name '{existing_alias}' ist bereits dem Topic {existing} zugeordnet.",
            409,
        )
    topic_manager.add_alias(chat_id, name, topic_id)
    logger.info(f"Topic-Verwaltung: Alias '{name}' -> Topic {topic_id} hinzugefügt.")
    return web.json_response({"status": "ok"})


async def handle_topic_alias_delete(request):
    if not get_authed_session(request):
        return _json_error("Unauthorized", 401)
    try:
        chat_id = resolve_topic_chat(request.query.get('chat_id'))
        name = validate_topic_name(request.query.get('name'))
    except ValueError as exc:
        return _json_error(str(exc))

    if not topic_manager.remove_alias(chat_id, name):
        return _json_error("Alias nicht gefunden.", 404)
    logger.info(f"Topic-Verwaltung: Alias '{name}' entfernt.")
    return web.json_response({"status": "ok"})


async def handle_dashboard_page(request):
    if get_authed_session(request):
        return web.Response(text=DASHBOARD_HTML, content_type='text/html')
    return web.Response(text=LOGIN_HTML, content_type='text/html')

async def handle_auth_request(request):
    token = secrets.token_hex(12)
    state.pending_auth[token] = {
        "status": "pending",
        "created_at": time.time(),
        "user": ""
    }
    # Aufräumen von Tokens älter als 10 Minuten
    now = time.time()
    for t in list(state.pending_auth.keys()):
        if now - state.pending_auth[t].get("created_at", 0) > 600:
            del state.pending_auth[t]

    deep_link = f"https://t.me/{state.bot_username}?start=login_{token}" if state.bot_username else f"https://t.me/?start=login_{token}"
    return web.json_response({
        "token": token,
        "bot_username": state.bot_username,
        "deep_link": deep_link
    })

async def handle_auth_check(request):
    token = request.query.get("token")
    if not token or token not in state.pending_auth:
        return web.json_response({"status": "expired"})

    info = state.pending_auth[token]
    status = info.get("status", "pending")
    if status == "approved":
        session_id = secrets.token_urlsafe(32)
        user_name = info.get("user", "Admin")
        state.active_sessions[session_id] = {
            "user": user_name,
            "expires_at": time.time() + (86400 * 30)  # 30 Tage gültig
        }
        del state.pending_auth[token]
        resp = web.json_response({"status": "approved", "user": user_name})
        resp.set_cookie("vod_session", session_id, max_age=86400 * 30, path="/", secure=True, httponly=True, samesite="Lax")
        return resp

    return web.json_response({"status": status})

async def handle_logout(request):
    session_id = request.cookies.get("vod_session")
    if session_id and session_id in state.active_sessions:
        del state.active_sessions[session_id]
    resp = web.json_response({"status": "ok"})
    resp.del_cookie("vod_session", path="/")
    return resp

async def handle_dashboard_status(request):
    session = get_authed_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401)

    topic_count = count_mapped_topics()
    return web.json_response({
        "user": session.get("user", "Admin"),
        "queue_count": len(state.waiting_queue),
        "topic_count": topic_count,
        "active_job": state.active_job,
        "queue": list(state.waiting_queue),
        "history": list(state.history),
        "logs": list(state.log_buffer),
        "rss": rss_archiver.status(),
        "n8n_workflows": sorted(N8N_WEBHOOKS)
    })

async def handle_dashboard_events(request):
    session = get_authed_session(request)
    if not session:
        return web.Response(status=401, text="Unauthorized")

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    await response.prepare(request)

    queue = asyncio.Queue()
    state.sse_queues.add(queue)

    try:
        topic_count = count_mapped_topics()
        init_data = {
            "user": session.get("user", "Admin"),
            "queue_count": len(state.waiting_queue),
            "topic_count": topic_count,
            "active_job": state.active_job,
            "queue": list(state.waiting_queue),
            "history": list(state.history),
            "logs": list(state.log_buffer),
            "rss": rss_archiver.status(),
            "n8n_workflows": sorted(N8N_WEBHOOKS)
        }
        await response.write(f"data: {json.dumps(init_data, ensure_ascii=False)}\n\n".encode('utf-8'))

        while True:
            await asyncio.sleep(1.5)
            topic_count = count_mapped_topics()
            data = {
                "user": session.get("user", "Admin"),
                "queue_count": len(state.waiting_queue),
                "topic_count": topic_count,
                "active_job": state.active_job,
                "queue": list(state.waiting_queue),
                "history": list(state.history),
                "logs": list(state.log_buffer),
                "rss": rss_archiver.status(),
                "n8n_workflows": sorted(N8N_WEBHOOKS)
            }
            await response.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode('utf-8'))
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        state.sse_queues.discard(queue)

    return response

async def on_startup(app):
    state.telegram_client = TelegramClient('vod_bot_session', API_ID, API_HASH)
    await state.telegram_client.start(bot_token=BOT_TOKEN)
    me = await state.telegram_client.get_me()
    state.bot_username = getattr(me, 'username', '') or ''
    logger.info(f"Telegram Bot @{state.bot_username} Client und Queue-Lock erfolgreich gestartet!")

    if RSS_ENABLED:
        rss_archiver.start()
        logger.info(
            "RSS-Archiv aktiviert (OPML: %s, Feed-URLs: %d, Feed-Filter: %s, Intervall: %ss, "
            "Retries: %s, Retry-Backoff: %ss-%ss, Live-Recheck: %ss, yt-dlp-Fragmente: %d).",
            RSS_OPML_FILE or "-",
            len(RSS_FEED_URLS),
            ", ".join(RSS_FEED_TITLES) if RSS_FEED_TITLES else "alle Feeds",
            RSS_POLL_INTERVAL,
            "unbegrenzt" if RSS_MAX_RETRIES <= 0 else RSS_MAX_RETRIES,
            RSS_RETRY_BASE_SECONDS,
            RSS_RETRY_MAX_DELAY_SECONDS,
            RSS_LIVE_RECHECK_SECONDS,
            YTDLP_CONCURRENT_FRAGMENTS,
        )
    else:
        logger.info("RSS-Archiv ist deaktiviert (RSS_ENABLED=false).")

    # Registriere Telegram Bot Chat Event-Handler für Option B Dashboard Auth
    @state.telegram_client.on(events.NewMessage(pattern=r'^/start(?:\s+login_([a-zA-Z0-9_-]+))?'))
    async def handle_tg_start(event):
        if not event.is_private:
            return
        token = event.pattern_match.group(1) if event.pattern_match else None
        sender = await event.get_sender()
        username = getattr(sender, 'username', None)
        first_name = getattr(sender, 'first_name', '') or ''
        user_handle = f"@{username}".lower() if username else ""
        user_id_str = str(sender.id)

        allowed_list = [u.strip().lower() for u in ALLOWED_DASHBOARD_USERS.split(',') if u.strip()]
        is_allowed = any(
            u == user_handle or u == (username or '').lower() or u == user_id_str
            for u in allowed_list
        )

        if not is_allowed:
            logger.warning(f"Unbefugter Dashboard Login-Versuch von @{username} (ID {sender.id})")
            await event.respond("⛔ **Zugriff verweigert:** Dein Telegram-Account ist nicht für das VOD-Dashboard freigeschaltet.")
            if token and token in state.pending_auth:
                state.pending_auth[token]["status"] = "denied"
            return

        if not token or token not in state.pending_auth:
            await event.respond(
                f"👋 Hallo {first_name}!\n\n"
                f"Ich bin dein VOD-Uploader Bot. Rufe `https://02njtne.cserverhost.cloud/voduploader` im Browser auf, um dich am Dashboard anzumelden."
            )
            return

        state.pending_auth[token]["user"] = f"@{username}" if username else (first_name or user_id_str)
        buttons = [
            [
                Button.inline("✅ Anmelden freigeben", data=f"auth_ok:{token}".encode('utf-8')),
                Button.inline("❌ Ablehnen", data=f"auth_no:{token}".encode('utf-8'))
            ]
        ]
        await event.respond(
            f"🔐 **Login-Anfrage für VOD Dashboard**\n\n"
            f"👤 Account: `@{username or sender.id}`\n"
            f"🌐 URL: `https://02njtne.cserverhost.cloud/voduploader`\n"
            f"⏱ Gültig für 5 Minuten.\n\n"
            f"Möchtest du diese Anmeldung jetzt freigeben?",
            buttons=buttons
        )

    @state.telegram_client.on(events.CallbackQuery(pattern=rb'^auth_(ok|no):(.+)'))
    async def handle_tg_auth_callback(event):
        action = event.pattern_match.group(1).decode('utf-8')
        token = event.pattern_match.group(2).decode('utf-8')
        sender = await event.get_sender()
        username = getattr(sender, 'username', None)
        user_handle = f"@{username}".lower() if username else ""
        user_id_str = str(sender.id)

        allowed_list = [u.strip().lower() for u in ALLOWED_DASHBOARD_USERS.split(',') if u.strip()]
        is_allowed = any(
            u == user_handle or u == (username or '').lower() or u == user_id_str
            for u in allowed_list
        )
        if not is_allowed:
            await event.answer("⛔ Zugriff verweigert!", alert=True)
            return

        if token not in state.pending_auth:
            await event.edit("⚠️ Diese Login-Anfrage ist abgelaufen oder ungültig.")
            await event.answer("Abgelaufen")
            return

        if action == "ok":
            state.pending_auth[token]["status"] = "approved"
            await event.edit("✅ **Anmeldung erfolgreich freigegeben!**\nDu bist jetzt im Dashboard angemeldet. Du kannst zum Browser zurückkehren.")
            await event.answer("Erfolgreich freigegeben! 🎉")
        else:
            state.pending_auth[token]["status"] = "denied"
            await event.edit("❌ **Anmeldung wurde abgelehnt.**")
            await event.answer("Abgelehnt")

async def on_cleanup(app):
    rss_archiver.stop()
    if state.telegram_client:
        await state.telegram_client.disconnect()
        logger.info("Telegram Bot Client getrennt.")

def create_app():
    app = web.Application()
    app.router.add_post('/upload', handle_upload)
    app.router.add_get('/health', handle_health)
    app.router.add_post('/rss/check', handle_rss_check)
    app.router.add_get('/rss/status', handle_rss_status)
    app.router.add_post('/rss/backfill', handle_rss_backfill)
    # Alias unter dem Traefik-Prefix, damit das Dashboard den Endpunkt erreicht.
    app.router.add_post('/voduploader/rss/check', handle_rss_check)
    app.router.add_get('/voduploader/rss/status', handle_rss_status)
    app.router.add_post('/voduploader/rss/backfill', handle_rss_backfill)

    # n8n-Workflow-Trigger (Dashboard-Buttons)
    app.router.add_post('/n8n/run', handle_n8n_run)
    app.router.add_post('/voduploader/n8n/run', handle_n8n_run)

    # Dashboard & Auth Endpunkte
    app.router.add_get('/voduploader', handle_dashboard_page)
    app.router.add_get('/voduploader/', handle_dashboard_page)
    app.router.add_post('/voduploader/api/auth/request', handle_auth_request)
    app.router.add_get('/voduploader/api/auth/check', handle_auth_check)
    app.router.add_post('/voduploader/api/logout', handle_logout)
    app.router.add_get('/voduploader/api/status', handle_dashboard_status)
    app.router.add_get('/voduploader/api/events', handle_dashboard_events)

    # Topic-Verwaltung
    app.router.add_get('/voduploader/topics', handle_topics_page)
    app.router.add_get('/voduploader/topics/', handle_topics_page)
    app.router.add_get('/voduploader/api/topics', handle_topics_list)
    app.router.add_post('/voduploader/api/topics', handle_topic_create)
    app.router.add_patch('/voduploader/api/topics', handle_topic_update)
    app.router.add_delete('/voduploader/api/topics', handle_topic_delete)
    app.router.add_post('/voduploader/api/topics/alias', handle_topic_alias_create)
    app.router.add_delete('/voduploader/api/topics/alias', handle_topic_alias_delete)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080)
