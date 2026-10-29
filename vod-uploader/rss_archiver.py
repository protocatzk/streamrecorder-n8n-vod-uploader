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

# Fehler, bei denen ein erneuter Versuch dauerhaft aussichtslos ist.
PERMANENT_HINTS = NO_VIDEO_HINTS + (
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
    "requested format is not available",
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


def _ytdlp_options(
    cookies_file: str | None,
    *,
    retries: int = 10,
    concurrent_fragments: int = 4,
    http_chunk_size: int = 10 * 1024 * 1024,
    buffer_size: int = 1024 * 1024,
) -> dict:
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
    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
    return opts


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
) -> dict:
    """Prueft per yt-dlp, ob die URL ein (archivierbares) Video enthaelt."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - sollte im Image vorhanden sein
        raise RuntimeError("yt-dlp ist nicht installiert") from exc

    opts = _ytdlp_options(
        cookies_file,
        retries=retries,
        concurrent_fragments=concurrent_fragments,
        http_chunk_size=http_chunk_size,
    )
    opts["skip_download"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

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

    opts = _ytdlp_options(
        cookies_file,
        retries=retries,
        concurrent_fragments=concurrent_fragments,
        http_chunk_size=http_chunk_size,
    )
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

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        if live_detected["flag"]:
            raise LiveStream(live_detected["message"]) from exc
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
        self.fetch_concurrency = max(1, int(fetch_concurrency))
        self.startup_delay = max(0, int(startup_delay))
        self.ytdlp_concurrent_fragments = max(1, int(ytdlp_concurrent_fragments))
        self.ytdlp_retries = max(0, int(ytdlp_retries))
        self.ytdlp_http_chunk_size = max(0, int(ytdlp_http_chunk_size))
        self.ytdlp_format = (ytdlp_format or "").strip() or None

        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._manual_task: asyncio.Task | None = None
        self._stopping = False
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
        entry = {
            "t": int(time.time()),
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
        for key in [k for k, v in items.items() if v.get("t", 0) < cutoff]:
            items.pop(key, None)

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
            "running": self._lock.locked(),
            "interval_seconds": self.interval,
            "max_retries": self.max_retries,
            "retry_base_seconds": self.retry_base_seconds,
            "retry_max_delay_seconds": self.retry_max_delay_seconds,
            "live_recheck_seconds": self.live_recheck_seconds,
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
            "counts": self._counts(),
            "feeds": feeds,
            "recent": list(self._recent[-15:]),
        }

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": self._lock.locked(),
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

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._stopping = True
        for task in (self._task, self._manual_task):
            if task and not task.done():
                task.cancel()

    async def _loop(self) -> None:
        try:
            if self.startup_delay:
                await asyncio.sleep(self.startup_delay)
            while not self._stopping:
                try:
                    await self.poll(trigger="auto")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("RSS-Poll fehlgeschlagen: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("RSS-Poller gestoppt.")

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

                # Live zuerst, dann Retries, danach neue Items.
                def _candidate_priority(item: RssItem) -> tuple[int, float]:
                    status = self._state.get("items", {}).get(item.key, {}).get("s")
                    if status == "live":
                        return 0, item.published or 0
                    if status == "retry":
                        return 1, item.published or 0
                    return 2, item.published or 0

                candidates.sort(key=_candidate_priority)
                summary["new"] = len(candidates)
                if self.max_items_per_poll and len(candidates) > self.max_items_per_poll:
                    logger.info(
                        "RSS-Poll: %d Video(s) faellig, verarbeite zunaechst %d (Rest folgt im naechsten Lauf).",
                        len(candidates),
                        self.max_items_per_poll,
                    )
                    candidates = candidates[: self.max_items_per_poll]
                elif candidates:
                    logger.info("RSS-Poll: %d faellige(s) Video(s) gefunden.", len(candidates))

                for item in candidates:
                    if self._stopping:
                        break
                    await self._process_item(item, summary)
                    self._save_state()

                self._prune_state()
                self._save_state()
                summary["finished_at"] = time.time()
                self.last_summary = summary
                logger.info(
                    "RSS-Poll beendet: %d faellig, %d archiviert, %d uebersprungen, %d warten (retry/live), %d Fehler.",
                    summary["new"],
                    summary["archived"],
                    summary["skipped"],
                    summary["retry"] + summary["live"],
                    summary["failed"],
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

    async def _process_item(self, item: RssItem, summary: dict) -> None:
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
                if is_live_error(exc):
                    self._mark_live(item, summary, str(exc))
                elif is_permanent_error(exc):
                    self._mark_skipped(item, summary, str(exc))
                else:
                    await self._record_failure(item, summary, f"Probe: {exc}")
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
            elif status == "live":
                message = result.get("message") or "Live-Stream läuft noch"
                self._mark_live(item, summary, str(message))
            else:
                message = result.get("message") or result.get("error") or "unbekannt"
                if is_live_error(Exception(str(message))):
                    self._mark_live(item, summary, str(message))
                elif is_permanent_error(Exception(str(message))):
                    self._mark_skipped(item, summary, str(message))
                else:
                    await self._record_failure(item, summary, f"Pipeline: {message}")
        except Exception as exc:
            if isinstance(exc, LiveStream) or is_live_error(exc):
                self._mark_live(item, summary, str(exc))
            elif isinstance(exc, NotAVideo) or is_permanent_error(exc):
                self._mark_skipped(item, summary, str(exc))
            else:
                await self._record_failure(item, summary, f"{type(exc).__name__}: {exc}")

    async def _record_failure(self, item: RssItem, summary: dict, reason: str) -> None:
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
