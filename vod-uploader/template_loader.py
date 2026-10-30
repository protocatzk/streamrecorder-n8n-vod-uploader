"""Lädt die HTML-Templates und statischen Assets des Web-Dashboards.

Die Templates liegen als echte Dateien unter ``templates/``; CSS und JS unter
``static/``. Sie werden beim Start einmalig gelesen und im Prozess gecacht.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

_cache: dict[str, str] = {}


def load_template(name: str) -> str:
    """Liest ein Template aus ``templates/`` (gecacht)."""
    if name not in _cache:
        _cache[name] = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    return _cache[name]


LOGIN_HTML = load_template("login.html")
DASHBOARD_HTML = load_template("dashboard.html")
TOPICS_HTML = load_template("topics.html")
