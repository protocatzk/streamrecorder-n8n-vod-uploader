"""rss.app Feed-Archiver.

Liest eine rss.app-OPML (oder einzelne Feed-URLs), erkennt Video-Items in den
Feeds und archiviert sie. Die eigentliche Datei wird per yt-dlp aufgeloest,
weil rss.app selbst nur Post-/Watch-URLs und Thumbnails liefert.

Der Archiver besitzt bewusst keine Telegram-Logik: er ruft fuer jedes Video
einen Callback auf, den ``main.py`` mit der bestehenden Upload-Pipeline
verbindet.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable
from urllib.parse import urlparse

import aiohttp
import feedparser

logger = logging.getLogger('vod_uploader.rss')

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Hosts, deren URLs mit hoher Wahrscheinlichkeit eine Videodatei beschreiben.
VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "x.com", "twitter.com",
    "tiktok.com",
    "instagram.com",
    "twitch.tv",
    "facebook.com", "fb.watch",
    "vimeo.com",
    "reddit.com", "redd.it",
    "streamable.com",
    "odysee.com",
    "rumble.com",
    "bitchute.com",
    "dailymotion.com", "dai.ly",
    "vk.com", "vkvideo.ru",
    "bilibili.com",
    "kick.com",
)

# Plattformen, bei denen ein Treffer auch ein reiner Text-/Bild-Post sein kann.
PROBE_HOSTS = ("x.com", "twitter.com", "facebook.com", "instagram.com", "reddit.com", "redd.it", "vk.com")

PLATFORM_MAP = (
    (("youtube.com", "youtu.be", "youtube-nocookie.com"), "youtube"),
    (("x.com", "twitter.com"), "x"),
    (("tiktok.com",), "tiktok"),
    (("instagram.com",), "instagram"),
    (("twitch.tv",), "twitch"),
    (("facebook.com", "fb.watch"), "facebook"),
    (("vimeo.com",), "vimeo"),
    (("reddit.com", "redd.it"), "reddit"),
    (("streamable.com",), "streamable"),
    (("odysee.com",), "odysee"),
    (("rumble.com",), "rumble"),
    (("bitchute.com",), "bitchute"),
    (("dailymotion.com", "dai.ly"), "dailymotion"),
    (("vk.com", "vkvideo.ru"), "vk"),
    (("bilibili.com",), "bilibili"),
    (("kick.com",), "kick"),
)


class NotAVideo(Exception):
    """Item enthaelt kein abspielbares Video (Text-Post, Bild, ...)."""


class LiveStream(Exception):
    """URL ist ein laufender/angekuendigter Livestream oder eine Premiere."""


NO_VIDEO_HINTS = (
    "no video",
    "there is no video",
    "no media found",
    "unsupported url",
    "is not a video",
    "not a video",
)

# YouTube blockt Server-IPs regelmaessig mit einem Login-/Bot-Check. Das ist
# transient (Cookies/PO-Token/Proxy), aber ein Retry alle 15 Minuten macht es
# nur schlimmer -> eigener Fehlertyp mit globaler Pause.
BOT_CHECK_HINTS = (
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "not a bot",
    "too many requests",
    "http error 429",
)

# Dauerhafte Fehler, bei denen ein Retry nichts bringt.
MEMBERS_ONLY_HINTS = (
    "available to this channel's members",
    "available to this channel’s members",
    "members-only",
    "member-only",
    "join this channel",
    "channel members",
)

AGE_RESTRICTED_HINTS = (
    "confirm your age",
    "age-restricted",
    "inappropriate for some users",
)

# Fehler, bei denen ein erneuter Versuch dauerhaft aussichtslos ist.
PERMANENT_HINTS = NO_VIDEO_HINTS + MEMBERS_ONLY_HINTS + (
    "video unavailable",
    "this video is unavailable",
    "private video",
    "this video is private",
    "removed by the uploader",
    "has been removed",
    "account has been terminated",
    "account associated with this video has been terminated",
    "copyright grounds",
    "blocked it on copyright grounds",
    "not available in your country",
    "not made this video available in your country",
    # "requested format is not available" ist NICHT dauerhaft: das kann an
    # einem ungueltigen Cookie-Login oder einem Client-/PO-Token-Problem liegen
    # und wird mit Cookie-Fallback erneut versucht.
    # "This live stream recording is not available" ist kein laufender Stream,
    # sondern ein dauerhaft fehlendes Recording.
    "live stream recording is not available",
    "this live stream recording is not available",
    "http 404",
    "http 410",
    "http 451",
)

# Fehler, bei denen ein zweiter Versuch ohne Cookies sinnvoll ist (kaputte oder
# abgelaufene Login-Session liefert zwar Metadaten, aber keine Formate).
# Ein Bot-Check gehoert bewusst NICHT hierher: er ist meist video-/IP-bezogen
# und bedeutet nicht, dass die Cookie-Datei ungueltig ist.
COOKIE_FALLBACK_HINTS = (
    "requested format is not available",
    "the page needs to be reloaded",
    "login required",
)

# Hinweise auf Live/Upcoming/Premiere in yt-dlp-Fehlermeldungen.
LIVE_HINTS = (
    "live event will begin",
    "premieres in",
    "premiere in",
    "is live",
    "live stream",
    "live-stream",
    "is_upcoming",
    "will begin in",
    "stream is live",
    "live event",
)


def is_no_video_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in NO_VIDEO_HINTS)


def is_permanent_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in PERMANENT_HINTS)


def is_bot_check_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in BOT_CHECK_HINTS)


def is_members_only_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in MEMBERS_ONLY_HINTS)


def is_age_restricted_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in AGE_RESTRICTED_HINTS)


def is_cookie_fallback_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in COOKIE_FALLBACK_HINTS)


def is_live_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(hint in message for hint in LIVE_HINTS)


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def host_matches(url: str, hosts: Iterable[str]) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in hosts)


def is_video_url(url: str) -> bool:
    return host_matches(url, VIDEO_HOSTS)


def needs_probe(url: str) -> bool:
    return host_matches(url, PROBE_HOSTS)


def detect_platform(url: str) -> str:
    for hosts, name in PLATFORM_MAP:
        if host_matches(url, hosts):
            return name
    return "rss"


def clean_text(value: str | None, limit: int = 500) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


@dataclass
class RssFeed:
    title: str
    url: str
    source_url: str | None = None
    bundle: bool = False
    child_count: int = 0

    def public(self) -> dict:
        return {
            "title": self.title,
            "bundle": self.bundle,
            "child_count": self.child_count,
            "host": _host(self.source_url or self.url),
        }


@dataclass
class RssItem:
    key: str
    feed: str
    channel: str
    title: str
    url: str
    published: float | None = None
    thumbnail: str | None = None
    media_url: str | None = None
    description: str = ""
    platform: str = "rss"
    duration: float | None = None

    @property
    def recording_id(self) -> str:
        return f"rss-{self.key[:10]}"

    @property
    def published_iso(self) -> str:
        if not self.published:
            return ""
        return datetime.fromtimestamp(self.published, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def public(self) -> dict:
        return {
            "channel": self.channel,
            "title": self.title,
            "url": self.url,
            "published": self.published_iso,
            "platform": self.platform,
        }


class _YdlLogger:
    """Leitet yt-dlp-Ausgaben in unser Logging um (statt auf stdout)."""

    def debug(self, msg):
        pass

    def info(self, msg):
        logger.debug("yt-dlp: %s", msg)

    def warning(self, msg):
        logger.warning("yt-dlp: %s", msg)

    def error(self, msg):
        logger.error("yt-dlp: %s", msg)


# Cookie-Datei kann im Betrieb ausgetauscht werden. Wenn eine Session zwar den
# Bot-Check umgeht, aber keine Formate liefert, wird sie bis zur naechsten
# Aenderung der Datei (mtime) uebersprungen.
_COOKIE_STATE_LOCK = threading.Lock()
_COOKIE_STATE = {"mtime": None, "broken": False, "reason": ""}


def _cookie_mtime(path: str | None) -> float | None:
    if not path:
        return None
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _cookies_usable(path: str | None) -> bool:
    if not path or not os.path.exists(path):
        return False
    mtime = _cookie_mtime(path)
    with _COOKIE_STATE_LOCK:
        if _COOKIE_STATE["mtime"] != mtime:
            _COOKIE_STATE["mtime"] = mtime
            _COOKIE_STATE["broken"] = False
            _COOKIE_STATE["reason"] = ""
        return not _COOKIE_STATE["broken"]


def _mark_cookies_broken(path: str | None, reason: str) -> None:
    with _COOKIE_STATE_LOCK:
        _COOKIE_STATE["mtime"] = _cookie_mtime(path)
        _COOKIE_STATE["broken"] = True
        _COOKIE_STATE["reason"] = str(reason)[:300]


def _cookie_state() -> dict:
    with _COOKIE_STATE_LOCK:
        return dict(_COOKIE_STATE)


def _reset_cookie_state() -> None:
    with _COOKIE_STATE_LOCK:
        _COOKIE_STATE["mtime"] = None
        _COOKIE_STATE["broken"] = False
        _COOKIE_STATE["reason"] = ""


def _copy_cookie_file(path: str) -> str | None:
    """Kopiert die Cookie-Datei nach /tmp, damit yt-dlp sie beschreiben kann.

    Die Originaldatei bleibt dadurch unangetastet und kann im laufenden Betrieb
    ausgetauscht werden. yt-dlp schreibt rotierte Cookies in die Kopie.
    """
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="ytdlp-cookies-", suffix=".txt")
        with os.fdopen(fd, "wb") as dst, open(path, "rb") as src:
            shutil.copyfileobj(src, dst)
        os.chmod(temp_path, 0o600)
        return temp_path
    except OSError as exc:
        logger.warning("Konnte Cookie-Datei nicht kopieren (%s): %s", path, exc)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None


def _ytdlp_options(
    cookies_file: str | None,
    *,
    retries: int = 10,
    concurrent_fragments: int = 4,
    http_chunk_size: int = 10 * 1024 * 1024,
    buffer_size: int = 1024 * 1024,
    pot_provider_url: str | None = None,
    proxy: str | None = None,
) -> tuple[dict, str | None]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": max(0, int(retries)),
        "fragment_retries": max(0, int(retries)),
        "concurrent_fragment_downloads": max(1, int(concurrent_fragments)),
        "http_chunk_size": max(0, int(http_chunk_size)),
        "buffersize": max(64 * 1024, int(buffer_size)),
        "remote_components": ["ejs:github"],
        "logger": _YdlLogger(),
    }
    cookie_temp = None
    if cookies_file and _cookies_usable(cookies_file):
        cookie_temp = _copy_cookie_file(cookies_file)
        if cookie_temp:
            opts["cookiefile"] = cookie_temp
    if pot_provider_url:
        # bgutil HTTP-Provider (docker-compose.yml: bgutil-provider)
        opts["extractor_args"] = {
            "youtubepot-bgutilhttp": {"base_url": [pot_provider_url]},
        }
    if proxy:
        opts["proxy"] = proxy
    return opts, cookie_temp


def _live_message(info: dict) -> str:
    if info.get("live_status") == "is_upcoming" or info.get("is_upcoming"):
        return "Livestream/Premiere steht noch aus"
    return "Live-Stream läuft noch"


def _probe_sync(
    url: str,
    cookies_file: str | None,
    allow_live: bool,
    *,
    retries: int = 10,
    concurrent_fragments: int = 4,
    http_chunk_size: int = 10 * 1024 * 1024,
    pot_provider_url: str | None = None,
    proxy: str | None = None,
) -> dict:
    """Prueft per yt-dlp, ob die URL ein (archivierbares) Video enthaelt."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - sollte im Image vorhanden sein
        raise RuntimeError("yt-dlp ist nicht installiert") from exc

    opts, cookie_temp = _ytdlp_options(
        cookies_file,
        retries=retries,
        concurrent_fragments=concurrent_fragments,
        http_chunk_size=http_chunk_size,
        pot_provider_url=pot_provider_url,
        proxy=proxy,
    )
    try:
        opts["skip_download"] = True

        def _probe(options):
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = _probe(opts)
        except Exception as exc:
            if opts.get("cookiefile") and is_cookie_fallback_error(exc):
                logger.warning(
                    "yt-dlp-Probe mit Cookies fehlgeschlagen (%s). Versuche ohne Cookies "
                    "(Cookie-Session evtl. abgelaufen).",
                    exc,
                )
                _mark_cookies_broken(cookies_file, str(exc))
                fallback = dict(opts)
                fallback.pop("cookiefile", None)
                info = _probe(fallback)
            else:
                raise

        if not info:
            raise NotAVideo("Keine Videoinformationen gefunden")

        if info.get("_type") == "playlist":
            entries = [entry for entry in (info.get("entries") or []) if entry]
            if not entries:
                raise NotAVideo("Leere Playlist")
            info = entries[0]

        if not allow_live and (info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming")):
            raise LiveStream(_live_message(info))

        return info
    finally:
        if cookie_temp:
            try:
                os.remove(cookie_temp)
            except OSError:
                pass


def _download_sync(
    url: str,
    out_base: str,
    progress_callback: Callable[[int, int], None] | None,
    cookies_file: str | None,
    allow_live: bool,
    *,
    retries: int = 10,
    concurrent_fragments: int = 4,
    http_chunk_size: int = 10 * 1024 * 1024,
    format_selector: str | None = None,
    pot_provider_url: str | None = None,
    proxy: str | None = None,
) -> tuple[str, dict]:
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yt-dlp ist nicht installiert") from exc

    def hook(data):
        if not progress_callback:
            return
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            progress_callback(done, total)
        elif data.get("status") == "finished":
            total = data.get("total_bytes") or data.get("downloaded_bytes") or 0
            progress_callback(total, total)

    live_detected = {"flag": False, "message": "Live-Stream läuft noch"}

    opts, cookie_temp = _ytdlp_options(
        cookies_file,
        retries=retries,
        concurrent_fragments=concurrent_fragments,
        http_chunk_size=http_chunk_size,
        pot_provider_url=pot_provider_url,
        proxy=proxy,
    )
    try:
        opts.update({
            "outtmpl": {"default": out_base + ".%(ext)s"},
            "format": format_selector or "bestvideo*+bestaudio/best",
            "merge_output_format": "mp4",
            "overwrites": True,
            "continuedl": True,
            "progress_hooks": [hook],
        })

        def match_filter(info, *, incomplete=False):
            if not allow_live and (info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming")):
                live_detected["flag"] = True
                live_detected["message"] = _live_message(info)
                return "Live-Stream wird nicht archiviert"
            return None

        opts["match_filter"] = match_filter

        def _run_download(options):
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=True)

        try:
            info = _run_download(opts)
        except Exception as exc:
            if live_detected["flag"]:
                raise LiveStream(live_detected["message"]) from exc
            if opts.get("cookiefile") and is_cookie_fallback_error(exc):
                logger.warning(
                    "yt-dlp-Download mit Cookies fehlgeschlagen (%s). Versuche ohne Cookies "
                    "(Cookie-Session evtl. abgelaufen).",
                    exc,
                )
                _mark_cookies_broken(cookies_file, str(exc))
                fallback = dict(opts)
                fallback.pop("cookiefile", None)
                try:
                    info = _run_download(fallback)
                except Exception as retry_exc:
                    if live_detected["flag"]:
                        raise LiveStream(live_detected["message"]) from retry_exc
                    raise
            else:
                raise

        if live_detected["flag"] and not info:
            raise LiveStream(live_detected["message"])

        candidates: list[str] = []
        for downloaded in (info or {}).get("requested_downloads") or []:
            path = downloaded.get("filepath")
            if path and os.path.exists(path):
                candidates.append(path)
        if not candidates:
            candidates = [
                os.path.join(os.path.dirname(out_base), name)
                for name in os.listdir(os.path.dirname(out_base) or ".")
                if name.startswith(os.path.basename(out_base) + ".")
            ]
        candidates = [
            path for path in candidates
            if os.path.isfile(path) and not path.endswith((".part", ".ytdl", ".temp"))
        ]
        if not candidates:
            raise RuntimeError("yt-dlp hat keine Ausgabedatei erzeugt")

        final_path = max(candidates, key=os.path.getsize)
        return final_path, info or {}
    finally:
        if cookie_temp:
            try:
                os.remove(cookie_temp)
            except OSError:
                pass


class RssArchiver:
    def __init__(
        self,
        on_item: Callable[[RssItem], Awaitable[dict]],
        state_file: str = "rss_state.json",
        opml_file: str | None = None,
        feed_urls: Iterable[str] = (),
        feed_titles: Iterable[str] = (),
        interval: int = 900,
        initial_backfill: bool = False,
        max_item_age_hours: int = 48,
        max_items_per_poll: int = 10,
        max_retries: int = 0,
        retry_base_seconds: int = 900,
        retry_max_delay_seconds: int = 21600,
        live_recheck_seconds: int = 900,
        retention_days: int = 90,
        allow_live: bool = False,
        cookies_file: str | None = None,
        fetch_concurrency: int = 5,
        startup_delay: int = 20,
        enabled: bool = True,
        ytdlp_concurrent_fragments: int = 4,
        ytdlp_retries: int = 10,
        ytdlp_http_chunk_size: int = 10 * 1024 * 1024,
        ytdlp_format: str | None = None,
        pot_provider_url: str | None = None,
        proxy: str | None = None,
        bot_pause_seconds: int = 3600,
        live_max_age_days: int = 7,
        retry_max_age_days: int = 30,
        max_retries_per_poll: int = 3,
    ):
        self.on_item = on_item
        self.enabled = enabled
        self.state_file = state_file
        self.opml_file = opml_file
        self.feed_urls = [url.strip() for url in feed_urls if str(url).strip()]
        self.feed_titles = [title.strip() for title in feed_titles if str(title).strip()]
        self.interval = max(60, int(interval))
        self.initial_backfill = initial_backfill
        self.max_item_age_hours = max(0, int(max_item_age_hours))
        self.max_items_per_poll = max(0, int(max_items_per_poll))
        self.max_retries = max(0, int(max_retries))
        self.retry_base_seconds = max(60, int(retry_base_seconds))
        self.retry_max_delay_seconds = max(
            self.retry_base_seconds, int(retry_max_delay_seconds)
        )
        self.live_recheck_seconds = max(60, int(live_recheck_seconds))
        self.retention_days = max(1, int(retention_days))
        self.allow_live = allow_live
        self.cookies_file = cookies_file
        self._last_cookie_mtime = _cookie_mtime(cookies_file)
        self.fetch_concurrency = max(1, int(fetch_concurrency))
        self.startup_delay = max(0, int(startup_delay))
        self.ytdlp_concurrent_fragments = max(1, int(ytdlp_concurrent_fragments))
        self.ytdlp_retries = max(0, int(ytdlp_retries))
        self.ytdlp_http_chunk_size = max(0, int(ytdlp_http_chunk_size))
        self.ytdlp_format = (ytdlp_format or "").strip() or None
        self.pot_provider_url = (pot_provider_url or "").strip() or None
        self.proxy = (proxy or "").strip() or None
        self.bot_pause_seconds = max(0, int(bot_pause_seconds))
        self.live_max_age_days = max(0, int(live_max_age_days))
        self.retry_max_age_days = max(0, int(retry_max_age_days))
        self.max_retries_per_poll = max(0, int(max_retries_per_poll))

        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._manual_task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None
        self._stopping = False
        self._blocked_until = 0.0
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._queued_keys: set[str] = set()
        self._queue_seq = 0
        self._max_queue = max(1, self.max_items_per_poll * 2) if self.max_items_per_poll else 50
        self._worker_busy = False
        self._worker_summary = {
            "archived": 0,
            "skipped": 0,
            "failed": 0,
            "retry": 0,
            "live": 0,
            "deferred": 0,
        }
        self._state = self._load_state()
        if self._migrate_state():
            self._save_state()
        self._feeds: list[RssFeed] = []
        self._recent: list[dict] = []
        self.last_poll_started: float | None = None
        self.last_poll_finished: float | None = None
        self.last_trigger = ""
        self.last_error: str | None = None
        self.last_summary: dict = {}
        # Feeds direkt einlesen, damit das Dashboard sie schon vor dem ersten Poll zeigt.
        self.load_feeds()

    # ------------------------------------------------------------------ State

    def _load_state(self) -> dict:
        state = {"version": 2, "initialized": False, "items": {}, "feeds": {}}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as handle:
                    content = handle.read().strip()
                if content:
                    loaded = json.loads(content)
                    if isinstance(loaded, dict):
                        state.update(loaded)
            except Exception as exc:
                logger.warning("Konnte RSS-State '%s' nicht lesen: %s", self.state_file, exc)
        state.setdefault("items", {})
        state.setdefault("feeds", {})
        return state

    def _migrate_state(self) -> bool:
        """Holt alte Endzustaende zurueck, damit nichts mehr nach 2 Versuchen verloren geht."""
        try:
            version = int(self._state.get("version") or 1)
        except (TypeError, ValueError):
            version = 1
        if version >= 2:
            return False

        changed = 0
        for entry in self._state.get("items", {}).values():
            if not isinstance(entry, dict):
                continue
            status = entry.get("s")
            if status == "failed":
                # Alte Logik hat nach max_retries endgueltig verworfen.
                entry["s"] = "retry"
                entry["n"] = 0
                entry["next"] = 0
                changed += 1
            elif status == "skipped" and is_live_error(Exception(str(entry.get("r") or ""))):
                entry["s"] = "live"
                entry["n"] = 0
                entry["next"] = 0
                changed += 1

        self._state["version"] = 2
        if changed:
            logger.info("RSS-State migriert: %d zuvor verworfene Item(s) wieder aktiviert.", changed)
        return True

    def _save_state(self) -> None:
        try:
            items = self._state.get("items", {})
            if len(items) > 20000:
                newest = sorted(items.items(), key=lambda kv: kv[1].get("t", 0), reverse=True)[:20000]
                self._state["items"] = dict(newest)
            directory = os.path.dirname(self.state_file) or "."
            os.makedirs(directory, exist_ok=True)
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as handle:
                json.dump(self._state, handle, ensure_ascii=False)
            try:
                os.replace(temp_file, self.state_file)
            except OSError:
                shutil.copyfile(temp_file, self.state_file)
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except Exception as exc:
            logger.warning("Konnte RSS-State '%s' nicht schreiben: %s", self.state_file, exc)

    def _attempts(self, key: str) -> int:
        return int(self._state.get("items", {}).get(key, {}).get("n", 0) or 0)

    def _next_retry(self, key: str) -> float:
        entry = self._state.get("items", {}).get(key, {})
        try:
            return float(entry.get("next", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _retry_delay(self, attempts: int) -> int:
        """Exponentielles Backoff: 15m, 30m, 1h, 2h, 4h, max. 6h."""
        exponent = min(max(0, attempts - 1), 10)
        return min(self.retry_base_seconds * (2 ** exponent), self.retry_max_delay_seconds)

    def _seen(self, key: str) -> bool:
        entry = self._state.get("items", {}).get(key)
        if not entry:
            return False
        status = entry.get("s")
        if status in ("archived", "skipped", "failed", "baseline"):
            return True
        if status == "live":
            # Live/Premiere bleibt in Beobachtung, bis yt-dlp kein Live mehr meldet.
            return self._next_retry(key) > time.time()
        if status == "retry":
            if self.max_retries and self._attempts(key) >= self.max_retries:
                return True
            return self._next_retry(key) > time.time()
        return False

    def _mark(
        self,
        item: RssItem,
        status: str,
        reason: str = "",
        attempts: int = 0,
        next_retry: float = 0,
    ) -> None:
        existing = self._state.get("items", {}).get(item.key) or {}
        entry = {
            "t": int(time.time()),
            "first": int(existing.get("first") or existing.get("t") or time.time()),
            "s": status,
            "ch": item.channel[:120],
            "ti": item.title[:180],
            "r": reason[:240],
            "n": attempts,
        }
        # Genug Daten fuer einen spaeteren Retry, auch wenn das Item aus dem Feed faellt.
        if item.url:
            entry["u"] = item.url[:2000]
        if item.feed:
            entry["f"] = item.feed[:200]
        if item.published:
            entry["p"] = int(item.published)
        if item.thumbnail:
            entry["th"] = item.thumbnail[:2000]
        if item.media_url:
            entry["m"] = item.media_url[:2000]
        if item.platform:
            entry["pl"] = item.platform[:40]
        if item.duration:
            entry["d"] = float(item.duration)
        if next_retry:
            entry["next"] = int(next_retry)
        self._state.setdefault("items", {})[item.key] = entry

    def _item_from_state(self, key: str, entry: dict) -> RssItem | None:
        url = str(entry.get("u") or "").strip()
        if not url:
            # Alte State-Eintraege ohne URL koennen erst beim naechsten Feed-Auftauchen
            # wieder verarbeitet werden.
            return None
        published = entry.get("p")
        try:
            published_value = float(published) if published else None
        except (TypeError, ValueError):
            published_value = None
        try:
            duration = float(entry["d"]) if entry.get("d") else None
        except (TypeError, ValueError):
            duration = None
        return RssItem(
            key=key,
            feed=str(entry.get("f") or ""),
            channel=str(entry.get("ch") or ""),
            title=str(entry.get("ti") or "(ohne Titel)"),
            url=url,
            published=published_value,
            thumbnail=str(entry.get("th") or "") or None,
            media_url=str(entry.get("m") or "") or None,
            platform=str(entry.get("pl") or detect_platform(url)),
            duration=duration,
        )

    def _prune_state(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)
        items = self._state.get("items", {})
        for key in [
            k for k, v in items.items()
            if (v.get("first") or v.get("t", 0)) < cutoff
        ]:
            items.pop(key, None)

    def _expire_state_items(self) -> int:
        """Gibt Retry-/Live-Items nach ihrer Maximalfrist endgueltig auf."""
        now = time.time()
        expired = 0
        items = self._state.get("items", {})
        for key, entry in list(items.items()):
            if not isinstance(entry, dict):
                continue
            status = entry.get("s")
            first = entry.get("first") or entry.get("t") or 0
            reason = None
            if (
                status == "retry"
                and self.retry_max_age_days
                and first
                and first < now - self.retry_max_age_days * 86400
            ):
                reason = f"Retry-Frist von {self.retry_max_age_days} Tagen abgelaufen"
            elif (
                status == "live"
                and self.live_max_age_days
                and first
                and first < now - self.live_max_age_days * 86400
            ):
                reason = (
                    f"Livestream/Premiere seit {self.live_max_age_days} Tagen "
                    "nicht verfuegbar"
                )
            if not reason:
                continue
            entry["s"] = "skipped"
            entry["r"] = reason[:240]
            entry["next"] = 0
            expired += 1
            self._recent.append({
                "time": int(now),
                "channel": str(entry.get("ch") or ""),
                "title": str(entry.get("ti") or "(ohne Titel)"),
                "status": "skipped",
                "reason": reason[:240],
            })
            logger.info(
                "RSS: '%s' (%s) endgueltig aufgegeben: %s",
                entry.get("ti") or key,
                entry.get("ch") or "-",
                reason,
            )
        return expired

    # ------------------------------------------------------------------ Feeds

    @staticmethod
    def parse_opml(path: str) -> list[RssFeed]:
        tree = ET.parse(path)
        body = tree.getroot().find("body")
        feeds: list[RssFeed] = []
        if body is None:
            return feeds

        def walk(node):
            xml_url = (node.get("xmlUrl") or "").strip()
            children = [child for child in list(node) if child.tag.lower() == "outline"]
            if xml_url:
                title = (
                    node.get("title")
                    or node.get("text")
                    or os.path.basename(xml_url)
                ).strip()
                feeds.append(RssFeed(
                    title=title or xml_url,
                    url=xml_url,
                    source_url=(node.get("htmlUrl") or "").strip() or None,
                    bundle=bool(children),
                    child_count=len(children),
                ))
                # Unterfeeds eines Bundles werden nicht separat gepollt.
                return
            for child in children:
                walk(child)

        for node in list(body):
            if node.tag.lower() == "outline":
                walk(node)
        return feeds

    def load_feeds(self) -> list[RssFeed]:
        feeds: list[RssFeed] = []
        opml_error = None

        if self.opml_file and os.path.exists(self.opml_file):
            try:
                feeds = self.parse_opml(self.opml_file)
            except Exception as exc:
                opml_error = f"OPML konnte nicht gelesen werden: {exc}"
                logger.error(opml_error)
        elif self.opml_file:
            opml_error = f"OPML-Datei nicht gefunden: {self.opml_file}"
            logger.warning(opml_error)

        known = {feed.url for feed in feeds}
        for url in self.feed_urls:
            if url not in known:
                feeds.append(RssFeed(title=_host(url) or url, url=url))
                known.add(url)

        if self.feed_titles:
            if feeds and self.opml_file and os.path.exists(self.opml_file):
                wanted = {title.casefold() for title in self.feed_titles}
                available = {feed.title.strip().casefold() for feed in feeds}
                missing = wanted - available
                if missing:
                    logger.warning(
                        "RSS_FEED_TITLES enthaelt unbekannte Titel: %s. Verfuegbar: %s",
                        ", ".join(sorted(missing)),
                        ", ".join(sorted(available))[:500],
                    )
                filtered = [feed for feed in feeds if feed.title.strip().casefold() in wanted]
                if filtered:
                    feeds = filtered
                else:
                    logger.error(
                        "Kein Feed in der OPML passt zu RSS_FEED_TITLES=%s - es wird nichts gepollt.",
                        ", ".join(self.feed_titles),
                    )
                    feeds = []
            else:
                logger.warning(
                    "RSS_FEED_TITLES ist gesetzt, aber keine OPML vorhanden - Titel-Filter wird ignoriert."
                )

        deduped: list[RssFeed] = []
        seen_urls = set()
        for feed in feeds:
            if feed.url in seen_urls:
                continue
            seen_urls.add(feed.url)
            deduped.append(feed)

        if opml_error and not deduped:
            self.last_error = opml_error
        self._feeds = deduped
        return deduped

    # ------------------------------------------------------------------ Fetch

    @staticmethod
    def _entry_timestamp(entry) -> float | None:
        for key in ("published_parsed", "updated_parsed", "created_parsed"):
            value = entry.get(key)
            if value:
                try:
                    return float(calendar.timegm(value))
                except Exception:
                    continue
        return None

    @staticmethod
    def _entry_media_url(entry) -> str | None:
        for enclosure in getattr(entry, "enclosures", []) or []:
            if str(enclosure.get("type", "")).startswith("video/") and enclosure.get("href"):
                return enclosure["href"]
        for media in getattr(entry, "media_content", []) or []:
            if media.get("medium") == "video" or str(media.get("type", "")).startswith("video/"):
                url = media.get("url") or media.get("href")
                if url:
                    return url
        return None

    @staticmethod
    def _entry_thumbnail(entry) -> str | None:
        for thumb in getattr(entry, "media_thumbnail", []) or []:
            if thumb.get("url"):
                return thumb["url"]
        for media in getattr(entry, "media_content", []) or []:
            url = media.get("url") or media.get("href")
            if not url:
                continue
            if media.get("medium") in (None, "image") or str(media.get("type", "")).startswith("image/"):
                return url
        for enclosure in getattr(entry, "enclosures", []) or []:
            if str(enclosure.get("type", "")).startswith("image/") and enclosure.get("href"):
                return enclosure["href"]
        content = ""
        if getattr(entry, "content", None):
            content = entry.content[0].get("value", "") or ""
        content = content or entry.get("summary", "") or entry.get("description", "") or ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)', content, re.IGNORECASE)
        return match.group(1) if match else None

    def _to_item(self, feed: RssFeed, entry, fallback_title: str) -> RssItem | None:
        url = (entry.get("link") or entry.get("id") or "").strip()
        if not url:
            return None
        title = clean_text(entry.get("title"), limit=300) or "(ohne Titel)"
        channel = clean_text(
            entry.get("dc_creator") or entry.get("author") or fallback_title or feed.title,
            limit=120,
        ) or feed.title
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
        return RssItem(
            key=key,
            feed=feed.title,
            channel=channel,
            title=title,
            url=url,
            published=self._entry_timestamp(entry),
            thumbnail=self._entry_thumbnail(entry),
            media_url=self._entry_media_url(entry),
            description=clean_text(entry.get("summary") or entry.get("description"), limit=600),
            platform=detect_platform(url),
        )

    async def _fetch_feed(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, feed: RssFeed):
        async with semaphore:
            try:
                timeout = aiohttp.ClientTimeout(total=45, sock_connect=15)
                async with session.get(
                    feed.url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"},
                    timeout=timeout,
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")
                    raw = await response.read()
            except Exception as exc:
                return feed, [], f"{type(exc).__name__}: {exc}"

        parsed = feedparser.parse(raw)
        if parsed.bozo and not parsed.entries:
            bozo = getattr(parsed, "bozo_exception", "unbekannter Fehler")
            return feed, [], f"Feed nicht lesbar: {bozo}"

        feed_title = clean_text(parsed.feed.get("title") if parsed.feed else None, limit=200)
        items = []
        for entry in parsed.entries:
            item = self._to_item(feed, entry, feed_title)
            if item:
                items.append(item)
        return feed, items, None

    # ------------------------------------------------------------------ Video

    async def probe_video(self, url: str) -> dict:
        return await asyncio.to_thread(
            _probe_sync,
            url,
            self.cookies_file,
            self.allow_live,
            retries=self.ytdlp_retries,
            concurrent_fragments=self.ytdlp_concurrent_fragments,
            http_chunk_size=self.ytdlp_http_chunk_size,
            pot_provider_url=self.pot_provider_url,
            proxy=self.proxy,
        )

    async def download_video(
        self,
        url: str,
        out_base: str,
        progress_callback: Callable[[int, int], None] | None = None,
        probe: bool = False,
    ) -> str:
        if probe:
            await self.probe_video(url)
        path, _info = await asyncio.to_thread(
            _download_sync,
            url,
            out_base,
            progress_callback,
            self.cookies_file,
            self.allow_live,
            retries=self.ytdlp_retries,
            concurrent_fragments=self.ytdlp_concurrent_fragments,
            http_chunk_size=self.ytdlp_http_chunk_size,
            format_selector=self.ytdlp_format,
            pot_provider_url=self.pot_provider_url,
            proxy=self.proxy,
        )
        return path

    # ------------------------------------------------------------------ Poll

    def _counts(self) -> dict:
        counts = {
            "archived": 0,
            "skipped": 0,
            "failed": 0,
            "retry": 0,
            "live": 0,
            "baseline": 0,
        }
        for entry in self._state.get("items", {}).values():
            status = entry.get("s", "")
            if status in counts:
                counts[status] += 1
        return counts

    def _cookies_status(self) -> dict:
        info = {
            "path": self.cookies_file,
            "exists": bool(self.cookies_file and os.path.exists(self.cookies_file)),
            "mtime": None,
            "size": None,
            "usable": False,
            "broken": False,
            "reason": "",
        }
        if info["exists"]:
            try:
                stat = os.stat(self.cookies_file)
                info["mtime"] = stat.st_mtime
                info["size"] = stat.st_size
            except OSError:
                pass
        if not info["exists"]:
            # Datei wurde entfernt: alten "broken"-Status nicht weiter anzeigen.
            _reset_cookie_state()
        info["usable"] = _cookies_usable(self.cookies_file)
        state = _cookie_state()
        info["broken"] = bool(state.get("broken")) if info["exists"] else False
        info["reason"] = state.get("reason", "") if info["exists"] else ""
        if info["mtime"] and info["mtime"] != self._last_cookie_mtime:
            if self._blocked_until > time.time():
                logger.info(
                    "Cookie-Datei wurde ersetzt, hebe YouTube-Bot-Check-Pause auf."
                )
            self._blocked_until = 0.0
        self._last_cookie_mtime = info["mtime"]
        return info

    def status(self) -> dict:
        feeds = []
        for feed in self._feeds:
            info = self._state.get("feeds", {}).get(feed.url, {})
            feeds.append({
                **feed.public(),
                "last_check": info.get("c"),
                "ok": info.get("o"),
                "error": info.get("e"),
                "items": info.get("n", 0),
            })
        return {
            "enabled": self.enabled,
            "running": self._lock.locked() or self._worker_busy,
            "polling": self._lock.locked(),
            "processing": self._worker_busy,
            "queue": self._queue.qsize(),
            "blocked_until": self._blocked_until,
            "bot_pause_seconds": self.bot_pause_seconds,
            "cookies": self._cookies_status(),
            "pot_provider_url": self.pot_provider_url,
            "proxy_enabled": bool(self.proxy),
            "interval_seconds": self.interval,
            "max_retries": self.max_retries,
            "retry_base_seconds": self.retry_base_seconds,
            "retry_max_delay_seconds": self.retry_max_delay_seconds,
            "live_recheck_seconds": self.live_recheck_seconds,
            "live_max_age_days": self.live_max_age_days,
            "retry_max_age_days": self.retry_max_age_days,
            "max_retries_per_poll": self.max_retries_per_poll,
            "ytdlp_concurrent_fragments": self.ytdlp_concurrent_fragments,
            "ytdlp_retries": self.ytdlp_retries,
            "opml_file": self.opml_file,
            "opml_found": bool(self.opml_file and os.path.exists(self.opml_file)),
            "feed_titles": self.feed_titles,
            "last_poll_started": self.last_poll_started,
            "last_poll_finished": self.last_poll_finished,
            "last_trigger": self.last_trigger,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
            "worker_stats": dict(self._worker_summary),
            "counts": self._counts(),
            "feeds": feeds,
            "recent": list(self._recent[-15:]),
        }

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": self._lock.locked() or self._worker_busy,
            "polling": self._lock.locked(),
            "processing": self._worker_busy,
            "queue": self._queue.qsize(),
            "blocked_until": self._blocked_until,
            "interval_seconds": self.interval,
            "feeds": len(self._feeds),
            "last_poll_finished": self.last_poll_finished,
            "last_error": self.last_error,
            "counts": self._counts(),
        }

    def trigger(self) -> bool:
        if self._lock.locked():
            return False
        if self._manual_task and not self._manual_task.done():
            return False
        self._manual_task = asyncio.create_task(self.poll(trigger="manual"))
        return True

    def trigger_backfill(self, limit: int = 10) -> bool:
        if self._lock.locked():
            return False
        if self._manual_task and not self._manual_task.done():
            return False
        self._manual_task = asyncio.create_task(self.poll(trigger="backfill", backfill_limit=max(1, limit)))
        return True

    def reset_retries(self) -> int:
        """Setzt den Retry-Backoff aller wartenden Items zurueck (nach Cookie-Fix)."""
        now = int(time.time())
        reset = 0
        for entry in self._state.get("items", {}).values():
            if not isinstance(entry, dict):
                continue
            if entry.get("s") == "retry":
                entry["next"] = 0
                entry["t"] = now
                reset += 1
        if reset:
            self._blocked_until = 0.0
            self._save_state()
            logger.info("RSS: Retry-Backoff fuer %d Item(s) zurueckgesetzt.", reset)
        return reset

    def _enqueue(self, item: RssItem, priority: int) -> bool:
        if item.key in self._queued_keys:
            return False
        if self._queue.qsize() >= self._max_queue:
            return False
        self._queued_keys.add(item.key)
        self._queue_seq += 1
        self._queue.put_nowait((priority, item.published or 0, self._queue_seq, item))
        return True

    def start(self) -> None:
        self._stopping = False
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._stopping = True
        for task in (self._task, self._manual_task, self._worker_task):
            if task and not task.done():
                task.cancel()

    async def _loop(self) -> None:
        try:
            if self.startup_delay:
                await asyncio.sleep(self.startup_delay)
            while not self._stopping:
                started = time.time()
                try:
                    await self.poll(trigger="auto")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("RSS-Poll fehlgeschlagen: %s", exc, exc_info=True)
                elapsed = time.time() - started
                await asyncio.sleep(max(0.0, self.interval - elapsed))
        except asyncio.CancelledError:
            logger.info("RSS-Poller gestoppt.")

    async def _worker_loop(self) -> None:
        """Verarbeitet die Warteschlange sequenziell, waehrend neue Feeds gepollt werden."""
        logger.info("RSS-Worker gestartet.")
        while not self._stopping:
            try:
                _priority, _published, _seq, item = await self._queue.get()
            except asyncio.CancelledError:
                raise
            self._worker_busy = True
            try:
                await self._process_item(item, self._worker_summary)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "RSS-Worker: Verarbeitung von '%s' fehlgeschlagen: %s",
                    item.title,
                    exc,
                    exc_info=True,
                )
            finally:
                self._queued_keys.discard(item.key)
                self._worker_busy = False
                self._save_state()

    async def poll(self, trigger: str = "auto", backfill_limit: int = 0) -> dict:
        if self._lock.locked():
            return {"status": "busy"}

        async with self._lock:
            started = time.time()
            self.last_poll_started = started
            self.last_trigger = trigger
            self.last_error = None
            summary = {
                "status": "ok",
                "trigger": trigger,
                "started_at": started,
                "feeds": 0,
                "items": 0,
                "new": 0,
                "selected": 0,
                "queued": 0,
                "expired": 0,
                "archived": 0,
                "skipped": 0,
                "failed": 0,
                "retry": 0,
                "live": 0,
                "pending": 0,
                "baselined": 0,
                "feed_errors": 0,
            }

            try:
                expired = self._expire_state_items()
                if expired:
                    summary["expired"] = expired
                    self._save_state()

                feeds = self.load_feeds()
                summary["feeds"] = len(feeds)
                if not feeds:
                    self.last_error = self.last_error or "Keine RSS-Feeds konfiguriert"
                    logger.warning("RSS-Poll: %s", self.last_error)
                    summary["status"] = "no_feeds"
                    return summary

                logger.info("RSS-Poll gestartet (%s): %d Feed(s) werden geprueft.", trigger, len(feeds))
                connector = aiohttp.TCPConnector(limit=self.fetch_concurrency * 2)
                async with aiohttp.ClientSession(connector=connector) as session:
                    semaphore = asyncio.Semaphore(self.fetch_concurrency)
                    results = await asyncio.gather(
                        *[self._fetch_feed(session, semaphore, feed) for feed in feeds]
                    )

                collected: dict[str, RssItem] = {}
                now = int(time.time())
                for feed, items, error in results:
                    self._state.setdefault("feeds", {})[feed.url] = {
                        "t": feed.title,
                        "c": now,
                        "o": error is None,
                        "e": error,
                        "n": len(items),
                    }
                    if error:
                        summary["feed_errors"] += 1
                        logger.warning("RSS-Feed '%s' konnte nicht geladen werden: %s", feed.title, error)
                    for item in items:
                        collected.setdefault(item.key, item)

                # Wartende Retry-/Live-Items auch dann weiterverfolgen, wenn sie
                # inzwischen aus dem Feed-Fenster gefallen sind.
                pending_added = 0
                for key, entry in list(self._state.get("items", {}).items()):
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("s") not in ("retry", "live"):
                        continue
                    if key in collected or self._seen(key):
                        continue
                    pending = self._item_from_state(key, entry)
                    if pending:
                        collected[key] = pending
                        pending_added += 1
                summary["pending"] = pending_added
                if pending_added:
                    logger.info(
                        "RSS-Poll: %d wartende Retry-/Live-Item(s) ausserhalb des Feeds werden weiterverfolgt.",
                        pending_added,
                    )

                items_sorted = sorted(collected.values(), key=lambda item: item.published or 0)
                summary["items"] = len(items_sorted)

                if not self._state.get("initialized"):
                    for item in items_sorted:
                        self._mark(item, "baseline")
                    self._state["initialized"] = True
                    summary["baselined"] = len(items_sorted)
                    self._save_state()
                    if not self.initial_backfill and not backfill_limit:
                        logger.info(
                            "RSS-Erstlauf: %d vorhandene Items als gesehen markiert (kein Backfill).",
                            len(items_sorted),
                        )
                        summary["finished_at"] = time.time()
                        self.last_summary = summary
                        return summary
                    if not backfill_limit:
                        for item in items_sorted:
                            self._state["items"].pop(item.key, None)
                        summary["baselined"] = 0

                # Einmaliger Backfill: die neuesten N Baseline-Items werden nachtraeglich
                # verarbeitet, alle uebrigen bleiben dauerhaft als gesehen markiert.
                backfill_keys: set[str] = set()
                if backfill_limit:
                    eligible = [
                        item for item in items_sorted
                        if self._state.get("items", {}).get(item.key, {}).get("s") == "baseline"
                        and (item.media_url or is_video_url(item.url))
                    ]
                    eligible.sort(key=lambda item: item.published or 0, reverse=True)
                    selected = eligible[:backfill_limit]
                    for item in selected:
                        self._state["items"].pop(item.key, None)
                        backfill_keys.add(item.key)
                    summary["backfill_selected"] = len(selected)
                    logger.info(
                        "RSS-Backfill: %d von %d bestehenden Video(s) werden verarbeitet (Limit %d).",
                        len(selected),
                        len(eligible),
                        backfill_limit,
                    )

                cutoff = time.time() - (self.max_item_age_hours * 3600) if self.max_item_age_hours else None
                candidates: list[RssItem] = []
                for item in items_sorted:
                    if self._seen(item.key):
                        continue
                    entry = self._state.get("items", {}).get(item.key, {})
                    is_pending = entry.get("s") in ("retry", "live")
                    if (
                        cutoff
                        and item.published
                        and item.published < cutoff
                        and item.key not in backfill_keys
                        and not is_pending
                    ):
                        self._mark(item, "skipped", "zu alt")
                        summary["skipped"] += 1
                        continue
                    if not item.media_url and not is_video_url(item.url):
                        self._mark(item, "skipped", "kein Video")
                        summary["skipped"] += 1
                        continue
                    candidates.append(item)

                # Neue Videos zuerst, dann Live-Checks, danach Retries. So
                # verdrängen Altlasten keine frisch erschienenen Videos.
                def _candidate_priority(item: RssItem) -> tuple[int, float]:
                    status = self._state.get("items", {}).get(item.key, {}).get("s")
                    if status == "retry":
                        return 2, item.published or 0
                    if status == "live":
                        return 1, item.published or 0
                    return 0, item.published or 0

                candidates.sort(key=_candidate_priority)
                summary["new"] = len(candidates)
                selected_items: list[RssItem] = []
                retries_taken = 0
                for item in candidates:
                    status = self._state.get("items", {}).get(item.key, {}).get("s")
                    if status == "retry":
                        if (
                            self.max_retries_per_poll
                            and retries_taken >= self.max_retries_per_poll
                        ):
                            continue
                        retries_taken += 1
                    selected_items.append(item)
                    if (
                        self.max_items_per_poll
                        and len(selected_items) >= self.max_items_per_poll
                    ):
                        break
                summary["selected"] = len(selected_items)
                if len(candidates) > len(selected_items):
                    logger.info(
                        "RSS-Poll: %d Video(s) faellig, %d eingereiht (Rest folgt im naechsten Lauf).",
                        len(candidates),
                        len(selected_items),
                    )
                elif candidates:
                    logger.info("RSS-Poll: %d faellige(s) Video(s) gefunden.", len(candidates))

                queued = 0
                for item in selected_items:
                    status = self._state.get("items", {}).get(item.key, {}).get("s")
                    priority = 2 if status == "retry" else (1 if status == "live" else 0)
                    if self._enqueue(item, priority):
                        queued += 1
                summary["queued"] = queued
                summary["pending"] = self._queue.qsize()
                if queued < len(selected_items):
                    logger.info(
                        "RSS-Poll: Queue voll (%d), %d Video(s) warten auf den naechsten Lauf.",
                        self._queue.qsize(),
                        len(selected_items) - queued,
                    )

                self._prune_state()
                self._save_state()
                summary["finished_at"] = time.time()
                self.last_summary = summary
                logger.info(
                    "RSS-Poll beendet: %d faellig, %d eingereiht, %d in Queue, %d abgelaufen, %d Feed-Fehler.",
                    summary["new"],
                    summary["queued"],
                    self._queue.qsize(),
                    summary["expired"],
                    summary["feed_errors"],
                )
                return summary

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                summary["status"] = "error"
                summary["error"] = self.last_error
                logger.error("RSS-Poll abgebrochen: %s", exc, exc_info=True)
                return summary
            finally:
                self.last_poll_finished = time.time()

    def _mark_skipped(self, item: RssItem, summary: dict, reason: str) -> None:
        self._mark(item, "skipped", reason)
        summary["skipped"] += 1
        self._recent.append({
            "time": int(time.time()),
            "channel": item.channel,
            "title": item.title,
            "status": "skipped",
            "reason": reason[:240],
        })
        logger.info("RSS: '%s' (%s) uebersprungen: %s", item.title, item.channel, reason)

    def _mark_live(self, item: RssItem, summary: dict, reason: str) -> None:
        first = self._state.get("items", {}).get(item.key, {}).get("first") or 0
        age_base = item.published or first
        if (
            self.live_max_age_days
            and age_base
            and time.time() - age_base > self.live_max_age_days * 86400
        ):
            self._mark_skipped(
                item,
                summary,
                f"Livestream/Premiere seit {self.live_max_age_days} Tagen nicht verfuegbar",
            )
            return
        previous = self._state.get("items", {}).get(item.key, {}).get("s")
        attempts = self._attempts(item.key) + 1
        next_retry = time.time() + self.live_recheck_seconds
        self._mark(item, "live", reason, attempts=attempts, next_retry=next_retry)
        summary["live"] += 1
        if previous != "live":
            self._recent.append({
                "time": int(time.time()),
                "channel": item.channel,
                "title": item.title,
                "status": "live",
                "reason": reason[:240],
            })
        logger.info(
            "RSS: '%s' (%s) ist noch live/angekuendigt (%s), naechste Pruefung in %ss.",
            item.title,
            item.channel,
            reason,
            self.live_recheck_seconds,
        )

    def _defer_bot_pause(self, item: RssItem, summary: dict) -> None:
        """Stellt ein YouTube-Item waehrend der Bot-Check-Pause zurueck (ohne Netzwerk)."""
        entry = self._state.get("items", {}).get(item.key)
        if entry is not None:
            entry["next"] = max(int(entry.get("next") or 0), int(self._blocked_until))
        else:
            self._mark(
                item,
                "retry",
                "YouTube-Bot-Check: Pause aktiv",
                attempts=0,
                next_retry=self._blocked_until,
            )
        summary["deferred"] = summary.get("deferred", 0) + 1
        logger.debug(
            "RSS: '%s' wegen YouTube-Bot-Check-Pause bis %s zurueckgestellt.",
            item.title,
            datetime.fromtimestamp(self._blocked_until, tz=timezone.utc).strftime("%H:%M:%S"),
        )

    async def _handle_error(
        self,
        item: RssItem,
        summary: dict,
        exc: Exception,
        prefix: str = "",
    ) -> None:
        reason = f"{prefix}: {exc}" if prefix else f"{type(exc).__name__}: {exc}"
        if isinstance(exc, NotAVideo) or is_members_only_error(exc) or is_permanent_error(exc):
            self._mark_skipped(item, summary, str(exc))
        elif is_age_restricted_error(exc):
            await self._record_failure(
                item, summary, f"Altersbeschraenkt (Cookie-Account pruefen): {reason}"
            )
        elif is_bot_check_error(exc):
            await self._record_failure(item, summary, reason, bot_check=True)
        elif isinstance(exc, LiveStream) or is_live_error(exc):
            self._mark_live(item, summary, str(exc))
        else:
            await self._record_failure(item, summary, reason)

    async def _process_item(self, item: RssItem, summary: dict) -> None:
        if self._blocked_until > time.time() and item.platform == "youtube":
            self._defer_bot_pause(item, summary)
            return
        if not item.media_url and needs_probe(item.url):
            try:
                info = await self.probe_video(item.url)
                item.duration = info.get("duration") or item.duration
            except LiveStream as exc:
                self._mark_live(item, summary, str(exc))
                return
            except NotAVideo as exc:
                self._mark_skipped(item, summary, str(exc))
                return
            except Exception as exc:
                await self._handle_error(item, summary, exc, prefix="Probe")
                return
        logger.info(
            "RSS: Archiviere '%s' von %s (%s)...",
            item.title,
            item.channel,
            item.platform,
        )
        try:
            result = await self.on_item(item)
            status = str(result.get("status", "")).lower()
            if status == "success":
                self._mark(item, "archived")
                summary["archived"] += 1
                self._recent.append({
                    "time": int(time.time()),
                    "channel": item.channel,
                    "title": item.title,
                    "status": "archived",
                    "reason": "",
                })
            elif status == "cancelled":
                self._mark_skipped(item, summary, "manuell abgebrochen")
            elif status == "live":
                message = result.get("message") or "Live-Stream läuft noch"
                exc = Exception(str(message))
                if is_members_only_error(exc) or is_permanent_error(exc):
                    self._mark_skipped(item, summary, str(message))
                elif is_age_restricted_error(exc):
                    await self._record_failure(
                        item,
                        summary,
                        f"Altersbeschraenkt (Cookie-Account pruefen): {message}",
                    )
                else:
                    self._mark_live(item, summary, str(message))
            else:
                message = result.get("message") or result.get("error") or "unbekannt"
                exc = Exception(str(message))
                if is_members_only_error(exc) or is_permanent_error(exc):
                    self._mark_skipped(item, summary, str(message))
                elif is_age_restricted_error(exc):
                    await self._record_failure(
                        item,
                        summary,
                        f"Altersbeschraenkt (Cookie-Account pruefen): {message}",
                    )
                elif is_bot_check_error(exc):
                    await self._record_failure(
                        item, summary, f"Pipeline: {message}", bot_check=True
                    )
                elif is_live_error(exc):
                    self._mark_live(item, summary, str(message))
                else:
                    await self._record_failure(item, summary, f"Pipeline: {message}")
        except Exception as exc:
            await self._handle_error(item, summary, exc)

    async def _record_failure(
        self,
        item: RssItem,
        summary: dict,
        reason: str,
        bot_check: bool = False,
    ) -> None:
        if bot_check:
            now = time.time()
            was_paused = self._blocked_until > now
            if self.bot_pause_seconds:
                self._blocked_until = max(
                    self._blocked_until, now + self.bot_pause_seconds
                )
            if not was_paused:
                logger.warning(
                    "YouTube-Bot-Check erkannt. Pausiere YouTube-Downloads fuer %ss. "
                    "Bitte YTDLP_COOKIES_FILE und YTDLP_POT_PROVIDER_URL pruefen.",
                    self.bot_pause_seconds,
                )
            self.last_error = f"YouTube-Bot-Check: {reason}"[:500]
            reason = f"YouTube-Bot-Check: {reason}"
        attempts = self._attempts(item.key) + 1
        next_retry = 0
        if self.max_retries and attempts >= self.max_retries:
            status = "failed"
            summary["failed"] += 1
            delay = 0
        else:
            status = "retry"
            delay = self._retry_delay(attempts)
            next_retry = time.time() + delay
            summary["retry"] += 1
        self._mark(item, status, reason, attempts=attempts, next_retry=next_retry)
        self._recent.append({
            "time": int(time.time()),
            "channel": item.channel,
            "title": item.title,
            "status": status,
            "reason": reason[:240],
        })
        log = logger.warning if status == "retry" else logger.error
        if delay:
            log(
                "RSS: '%s' (%s) fehlgeschlagen (Versuch %d, naechster Versuch in %ss): %s",
                item.title,
                item.channel,
                attempts,
                delay,
                reason,
            )
        else:
            log(
                "RSS: '%s' (%s) endgueltig fehlgeschlagen (Versuch %d): %s",
                item.title,
                item.channel,
                attempts,
                reason,
            )
