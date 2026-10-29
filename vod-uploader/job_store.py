"""Persistenter Job-Spool fuer den VOD-Uploader.

Haelt angenommene Jobs inklusive Fortschritt (Download, Split, bereits
hochgeladene Telegram-Teile) auf einem Volume fest, damit ein Neustart oder
Deploy laufende Uploads nicht mehr verwirft.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:120] or "job"


def make_key(data: Dict[str, Any]) -> str:
    """Stabile Idempotenz-Kennung fuer einen Job."""
    recording_id = str(data.get("recording_id") or "").strip()
    source = str(data.get("source") or "streamrecorder").strip().lower()
    if recording_id:
        basis = f"{source}:{recording_id}"
    else:
        basis = str(
            data.get("download_url")
            or data.get("source_url")
            or json.dumps(data, sort_keys=True, default=str)
        )
        basis = f"{source}:{basis}"
    if len(basis) > 200:
        basis = "hash:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return _safe_name(basis)


class JobStore:
    """Atomarer JSON-Store fuer Job-Metadaten plus Job-Verzeichnisse."""

    def __init__(self, base_dir: str, done_ttl_days: int = 14, stale_days: int = 3):
        self.base_dir = os.path.abspath(base_dir)
        self.jobs_dir = os.path.join(self.base_dir, "jobs")
        self.jobs_file = os.path.join(self.base_dir, "jobs.json")
        self.done_file = os.path.join(self.base_dir, "done.json")
        self.done_ttl = max(1, done_ttl_days) * 86400
        self.stale_seconds = max(1, stale_days) * 86400

        os.makedirs(self.jobs_dir, exist_ok=True)
        self._jobs: Dict[str, Dict[str, Any]] = self._read(self.jobs_file, {})
        self._done: Dict[str, float] = self._read(self.done_file, {})
        self._prune_done()
        self._save_done()
        self._prune_dirs()

    # ------------------------------------------------------------------ io
    def _read(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default

    def _write(self, path: str, data: Any) -> None:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)

    def _save_jobs(self) -> None:
        self._write(self.jobs_file, self._jobs)

    def _save_done(self) -> None:
        self._write(self.done_file, self._done)

    # -------------------------------------------------------------- lookup
    @staticmethod
    def key_for(data: Dict[str, Any]) -> str:
        return make_key(data)

    def job_dir_for(self, key: str) -> str:
        return os.path.join(self.jobs_dir, key)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        record = self._jobs.get(key)
        return json.loads(json.dumps(record)) if record else None

    def is_done(self, key: str) -> bool:
        return key in self._done

    def pending(self) -> List[Dict[str, Any]]:
        records = [
            dict(record)
            for record in self._jobs.values()
            if record.get("status") in ("queued", "running")
        ]
        records.sort(key=lambda item: item.get("created_at", ""))
        return records

    # -------------------------------------------------------------- mutate
    def create(self, key: str, payload: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        existing = self.get(key)
        if existing:
            return existing

        record = {
            "key": key,
            "job_id": job_id,
            "payload": payload,
            "status": "queued",
            "stage": "queued",
            "attempts": 0,
            "error": None,
            "job_dir": self.job_dir_for(key),
            "downloaded": False,
            "downloaded_size": 0,
            "parts": [],
            "uploaded_message_ids": [],
            "forum_message_ids": [],
            "topic_id": None,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        os.makedirs(record["job_dir"], exist_ok=True)
        self._jobs[key] = record
        self._save_jobs()
        return json.loads(json.dumps(record))

    def update(self, key: str, **fields: Any) -> Dict[str, Any]:
        record = self._jobs.get(key)
        if record is None:
            raise KeyError(key)
        record.update(fields)
        record["updated_at"] = utcnow()
        self._save_jobs()
        return json.loads(json.dumps(record))

    def mark_running(self, key: str, stage: str | None = None) -> Dict[str, Any]:
        record = self._jobs.get(key)
        attempts = int((record or {}).get("attempts") or 0) + 1
        fields: Dict[str, Any] = {
            "status": "running",
            "attempts": attempts,
            "error": None,
        }
        if stage:
            fields["stage"] = stage
        return self.update(key, **fields)

    def complete(self, key: str, status: str = "done", remember: bool = True) -> None:
        record = self._jobs.pop(key, None)
        if record is not None:
            self._save_jobs()
        if remember:
            self._done[key] = time.time()
            self._save_done()
        self.remove_job_dir(key)

    def fail(self, key: str, error: str) -> None:
        self.update(key, status="failed", error=str(error)[:1000])

    def touch(self, key: str) -> None:
        self.update(key)

    # ------------------------------------------------------------- cleanup
    def remove_job_dir(self, key: str) -> None:
        shutil.rmtree(self.job_dir_for(key), ignore_errors=True)

    def _prune_done(self) -> None:
        cutoff = time.time() - self.done_ttl
        self._done = {key: ts for key, ts in self._done.items() if float(ts) >= cutoff}

    def _prune_dirs(self) -> None:
        referenced = {
            record.get("key") or key
            for key, record in self._jobs.items()
        }
        cutoff = time.time() - self.stale_seconds
        try:
            entries = os.listdir(self.jobs_dir)
        except OSError:
            return
        for entry in entries:
            path = os.path.join(self.jobs_dir, entry)
            if not os.path.isdir(path):
                continue
            if entry in referenced:
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)

    def summary(self) -> Dict[str, Any]:
        return {
            "dir": self.base_dir,
            "pending": len(self.pending()),
            "done_entries": len(self._done),
            "jobs": [
                {
                    "key": record.get("key"),
                    "job_id": record.get("job_id"),
                    "stage": record.get("stage"),
                    "status": record.get("status"),
                    "attempts": record.get("attempts"),
                }
                for record in self.pending()
            ],
        }
