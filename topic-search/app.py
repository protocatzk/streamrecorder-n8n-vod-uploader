import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("topic_search")

PORT = int(os.getenv("PORT", "8081"))
CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME", "RippersArchiv").strip().lstrip("@")
FORUM_CHAT_ID = os.getenv("FORUM_CHAT_ID", "-1004489497092").strip()
TOPICS_CACHE_FILE = os.getenv("TOPICS_CACHE_FILE", "/data/topics_cache.json")
VOD_INDEX_FILE = os.getenv("VOD_INDEX_FILE", "/data/state/vod_index.jsonl")
JOBS_FILE = os.getenv("JOBS_FILE", "/data/state/jobs.json")
MAX_VODS_PER_TOPIC = max(1, int(os.getenv("MAX_VODS_PER_TOPIC", "3")))

STATIC_DIR = Path(__file__).resolve().parent / "static"


def normalize_key(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(text or "")).lower()


def build_topic_url(topic_id: int) -> str:
    if CHANNEL_USERNAME:
        return f"https://t.me/{CHANNEL_USERNAME}/{topic_id}"
    chat_num = FORUM_CHAT_ID[4:] if FORUM_CHAT_ID.startswith("-100") else FORUM_CHAT_ID.lstrip("-")
    return f"https://t.me/c/{chat_num}/{topic_id}"


def build_vod_url(topic_id: int, message_id: int) -> str:
    return f"{build_topic_url(topic_id)}/{message_id}"


def _pick_display_name(aliases: list[str]) -> str:
    handles = [a for a in aliases if a.startswith("@")]
    if handles:
        return handles[0]
    return sorted(aliases, key=lambda x: (len(x), x.lower()))[0]


class SearchIndex:
    def __init__(self) -> None:
        self._topics_mtime: float | None = None
        self._index_mtime: float | None = None
        self._jobs_mtime: float | None = None
        self._topics: dict[int, dict[str, Any]] = {}
        self._vods_by_topic: dict[int, list[dict[str, Any]]] = {}
        self._total_indexed_vods: int = 0

    def _file_mtime(self, path: str) -> float | None:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return None

    def refresh_if_needed(self) -> None:
        t_mtime = self._file_mtime(TOPICS_CACHE_FILE)
        if t_mtime != self._topics_mtime:
            self._load_topics()
            self._topics_mtime = t_mtime

        i_mtime = self._file_mtime(VOD_INDEX_FILE)
        j_mtime = self._file_mtime(JOBS_FILE)
        if i_mtime != self._index_mtime or j_mtime != self._jobs_mtime:
            self._load_vods()
            self._index_mtime = i_mtime
            self._jobs_mtime = j_mtime

    def _load_topics(self) -> None:
        if not os.path.exists(TOPICS_CACHE_FILE):
            self._topics = {}
            return
        try:
            with open(TOPICS_CACHE_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:
            logger.warning("Konnte topics_cache.json nicht laden: %s", exc)
            return

        chat_map = raw.get(FORUM_CHAT_ID)
        if not isinstance(chat_map, dict) and raw:
            # Fallback auf ersten Chat-Eintrag, falls FORUM_CHAT_ID abweicht
            first_val = next(iter(raw.values()))
            if isinstance(first_val, dict):
                chat_map = first_val

        grouped: dict[int, list[str]] = {}
        if isinstance(chat_map, dict):
            for alias, tid in chat_map.items():
                if isinstance(tid, int) and not isinstance(tid, bool) and tid > 0:
                    grouped.setdefault(tid, []).append(str(alias).strip())

        topics: dict[int, dict[str, Any]] = {}
        for tid, aliases in grouped.items():
            unique_aliases = list(dict.fromkeys(a for a in aliases if a))
            if not unique_aliases:
                continue
            topics[tid] = {
                "topic_id": tid,
                "display_name": _pick_display_name(unique_aliases),
                "aliases": unique_aliases,
                "norm_aliases": [(a.lower(), normalize_key(a)) for a in unique_aliases],
                "topic_url": build_topic_url(tid),
            }
        self._topics = topics
        logger.info("Topic-Index aktualisiert: %d Topics geladen.", len(self._topics))

    def _load_vods(self) -> None:
        by_topic: dict[int, dict[int, dict[str, Any]]] = {}

        def add_entry(topic_id: int, message_id: int, item: dict[str, Any]) -> None:
            if topic_id <= 0 or message_id <= 0:
                return
            topic_bucket = by_topic.setdefault(topic_id, {})
            topic_bucket[message_id] = item

        if os.path.exists(VOD_INDEX_FILE):
            try:
                with open(VOD_INDEX_FILE, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        tid = row.get("topic_id")
                        msg_id = row.get("message_id")
                        if not tid or not msg_id:
                            mids = row.get("forum_message_ids") or row.get("message_ids") or []
                            msg_id = mids[0] if mids else None
                        if isinstance(tid, int) and isinstance(msg_id, int):
                            add_entry(
                                tid,
                                msg_id,
                                {
                                    "message_id": msg_id,
                                    "url": build_vod_url(tid, msg_id),
                                    "title": row.get("title") or "VOD",
                                    "streamer": row.get("streamer") or "",
                                    "platform": row.get("platform") or "",
                                    "duration": row.get("duration") or "",
                                    "size_mb": row.get("size_mb"),
                                    "recorded_at": row.get("recorded_at") or "",
                                    "finished_at": row.get("finished_at") or row.get("updated_at") or "",
                                    "parts": len(row.get("message_ids") or []) or 1,
                                },
                            )
            except Exception as exc:
                logger.warning("Konnte vod_index.jsonl nicht lesen: %s", exc)

        if os.path.exists(JOBS_FILE):
            try:
                with open(JOBS_FILE, "r", encoding="utf-8") as fh:
                    jobs_raw = json.load(fh)
                jobs = jobs_raw.get("jobs", jobs_raw) if isinstance(jobs_raw, dict) else {}
                if isinstance(jobs, dict):
                    for job in jobs.values():
                        if not isinstance(job, dict):
                            continue
                        tid = job.get("topic_id")
                        mids = job.get("forum_message_ids") or []
                        if isinstance(tid, int) and mids and isinstance(mids[0], int):
                            msg_id = mids[0]
                            payload = job.get("payload") or {}
                            add_entry(
                                tid,
                                msg_id,
                                {
                                    "message_id": msg_id,
                                    "url": build_vod_url(tid, msg_id),
                                    "title": payload.get("title") or job.get("title") or "VOD",
                                    "streamer": payload.get("streamer") or "",
                                    "platform": payload.get("platform") or "",
                                    "duration": payload.get("duration") or "",
                                    "size_mb": payload.get("filesize_mb"),
                                    "recorded_at": payload.get("recorded_at") or "",
                                    "finished_at": job.get("updated_at") or job.get("created_at") or "",
                                    "parts": len(mids),
                                },
                            )
            except Exception as exc:
                logger.warning("Konnte jobs.json nicht lesen: %s", exc)

        sorted_by_topic: dict[int, list[dict[str, Any]]] = {}
        total = 0
        for tid, items_map in by_topic.items():
            items = sorted(
                items_map.values(),
                key=lambda x: (x.get("finished_at") or "", x.get("recorded_at") or "", x.get("message_id") or 0),
                reverse=True,
            )
            sorted_by_topic[tid] = items
            total += len(items)

        self._vods_by_topic = sorted_by_topic
        self._total_indexed_vods = total

    def search(self, query: str, limit: int = 30) -> dict[str, Any]:
        self.refresh_if_needed()
        q_raw = (query or "").strip().lower()
        q_norm = normalize_key(q_raw)

        scored: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
        for tid, topic in self._topics.items():
            if not q_raw:
                vods = self._vods_by_topic.get(tid, [])
                # Ohne Suchbegriff: Topics mit VODs zuerst, dann alphabetisch
                score = (0 if vods else 1, -len(vods), topic["display_name"].lower())
                scored.append((score, topic))
                continue

            best_rank: int | None = None
            best_len = 9999
            for raw_alias, norm_alias in topic["norm_aliases"]:
                if raw_alias == q_raw or (q_norm and norm_alias == q_norm):
                    rank = 0
                elif raw_alias.startswith(q_raw) or (q_norm and norm_alias.startswith(q_norm)):
                    rank = 1
                elif q_raw in raw_alias or (q_norm and q_norm in norm_alias):
                    rank = 2
                else:
                    continue

                if best_rank is None or rank < best_rank or (rank == best_rank and len(raw_alias) < best_len):
                    best_rank = rank
                    best_len = len(raw_alias)

            if best_rank is not None:
                scored.append(((best_rank, best_len, topic["display_name"].lower()), topic))

        scored.sort(key=lambda item: item[0])
        results = []
        for _, topic in scored[:limit]:
            tid = topic["topic_id"]
            results.append(
                {
                    "topic_id": tid,
                    "display_name": topic["display_name"],
                    "aliases": topic["aliases"],
                    "topic_url": topic["topic_url"],
                    "vods": self._vods_by_topic.get(tid, [])[:MAX_VODS_PER_TOPIC],
                }
            )

        return {
            "query": query.strip(),
            "channel": f"@{CHANNEL_USERNAME}" if CHANNEL_USERNAME else FORUM_CHAT_ID,
            "total_topics": len(self._topics),
            "indexed_vods": self._total_indexed_vods,
            "count": len(results),
            "results": results,
        }


INDEX = SearchIndex()


async def handle_index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_search(request: web.Request) -> web.Response:
    q = request.query.get("q", "")
    try:
        limit = max(1, min(100, int(request.query.get("limit", "30"))))
    except ValueError:
        limit = 30
    data = INDEX.search(q, limit=limit)
    return web.json_response(data)


async def handle_health(request: web.Request) -> web.Response:
    INDEX.refresh_if_needed()
    return web.json_response(
        {
            "status": "ok",
            "topics": len(INDEX._topics),
            "indexed_vods": INDEX._total_indexed_vods,
        }
    )


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/search", handle_index)
    app.router.add_get("/search/", handle_index)
    app.router.add_get("/api/search", handle_search)
    app.router.add_get("/search/api/search", handle_search)
    app.router.add_get("/health", handle_health)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
