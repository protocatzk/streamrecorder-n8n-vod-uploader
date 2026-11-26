"""notube.cc Downloader.

notube.cc bietet keine oeffentliche API. Dieses Modul bildet den Ablauf der
Webseite nach:

1. freien Server (``s40`` ... ``s76``) waehlen
2. ``recover_weight.php``  -> Token, Dateiname und Groesse
3. ``recover_file.php``    -> Datei vorbereiten/konvertieren
4. ``/{lang}/download?token=...`` -> echter ``download.php``-Link
5. Datei streamen

Die Cookies einer Plus-Session werden aus einer Netscape-Cookie-Datei (oder
einem rohen Cookie-Header) gelesen. Die Datei wird bei jeder Anfrage neu
geladen, damit sie im laufenden Betrieb ausgetauscht werden kann.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import unquote_plus

import aiohttp

logger = logging.getLogger("vod_uploader.notube")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_SERVERS = tuple(range(40, 77))
_SUBSCRIPTION_TTL = 600.0
_DOWNLOAD_LINK_RE = re.compile(
    r"https?://s\d+\.notube\.cc/download\.php\?[^\"'\s<>]+",
    re.IGNORECASE,
)
_TURNSTILE_SITEKEY_RE = re.compile(r'data-sitekey=["\']([^"\']+)')


def _looks_like_challenge(text: str) -> bool:
    lowered = (text or "").lower()
    return (
        "cf-turnstile" in lowered
        or "challenges.cloudflare.com" in lowered
        or "turnstileCallback".lower() in lowered
    )


class NotubeError(Exception):
    """Allgemeiner notube-Fehler (standardmaessig wiederholbar)."""


class NotubeBusyError(NotubeError):
    """Server meldet ``HS``/Busy: anderer Server oder spaeter erneut versuchen."""


class NotubeLimitError(NotubeError):
    """Download-Limit erreicht (``exceeded``/``limitation``)."""


class NotubePlusRequiredError(NotubeError):
    """Video/Format ist nur mit notube Plus verfuegbar."""


class NotubePermanentError(NotubeError):
    """Dauerhafter Fehler (Video weg, privat, kein Video, nicht unterstuetzt)."""


class NotubeChallengeError(NotubeError):
    """Cloudflare Turnstile/Captcha blockiert den Download."""


@dataclass
class NotubeDownload:
    url: str
    filename: str
    size: int | None
    token: str


def parse_server_spec(spec: str | Iterable[int] | None) -> list[int]:
    """Wandelt ``40-76``, ``40,41,50`` oder eine Iterable in Server-IDs um."""
    if spec is None:
        return list(DEFAULT_SERVERS)
    if not isinstance(spec, str):
        values = [int(value) for value in spec]
        return values or list(DEFAULT_SERVERS)

    servers: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                servers.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                servers.append(int(part))
            except ValueError:
                continue
    return servers or list(DEFAULT_SERVERS)


def _cookie_pairs_from_text(text: str) -> list[tuple[str, str]]:
    """Erkennt Netscape-, JSON- und Roh-Header-Cookies."""
    text = (text or "").lstrip("\ufeff").strip()
    if not text:
        return []

    pairs: list[tuple[str, str]] = []

    # JSON-Export (z. B. EditThisCookie oder Browser-Erweiterung)
    if text.startswith(("[", "{")):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            data = data.get("cookies") or data.get("Cookies") or []
        if isinstance(data, list):
            for cookie in data:
                if not isinstance(cookie, dict):
                    continue
                name = str(cookie.get("name") or "").strip()
                value = str(cookie.get("value") or "")
                domain = str(cookie.get("domain") or "").lstrip(".").lower()
                if not name:
                    continue
                if domain and domain != "notube.cc" and not domain.endswith(".notube.cc"):
                    continue
                pairs.append((name, value))
            return pairs

    # Netscape-Cookie-Datei
    netscape = text.startswith("# Netscape") or any(
        len(line.split("\t")) >= 7
        for line in text.splitlines()
        if line and not line.startswith("#")
    )
    if netscape:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, _path, _secure, expiry, name, value = parts[:7]
            host = domain.lstrip(".").lower()
            if host != "notube.cc" and not host.endswith(".notube.cc"):
                continue
            if expiry and expiry.isdigit():
                expires = int(expiry)
                if expires and expires < time.time():
                    continue
            if name:
                pairs.append((name, value))
        return pairs

    # Roher Cookie-Header
    raw = text
    if raw.lower().startswith("cookie:"):
        raw = raw[7:]
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            pairs.append((name, value.strip()))
    return pairs


def _cookie_header_from_pairs(pairs: list[tuple[str, str]]) -> str:
    # Doppelte Namen (z. B. alte und neue Session) -> letzter Wert gewinnt.
    merged: dict[str, str] = {}
    for name, value in pairs:
        merged[name] = value
    return "; ".join(f"{name}={value}" for name, value in merged.items())


class NotubeClient:
    def __init__(
        self,
        *,
        cookies_file: str | None = None,
        cookie_header: str | None = None,
        lang: str = "de",
        format: str = "auto",
        servers: str | Iterable[int] | None = None,
        request_timeout: int = 3600,
        inactivity_timeout: int = 120,
        connect_timeout: int = 30,
        proxy: str | None = None,
        captcha_provider: str | None = None,
        captcha_api_key: str | None = None,
    ):
        self.cookies_file = (cookies_file or "").strip() or None
        self.raw_cookie_header = (cookie_header or "").strip() or None
        self.lang = (lang or "de").strip() or "de"
        self.format = (format or "auto").strip() or "auto"
        self.servers = parse_server_spec(servers)
        self.request_timeout = max(30, int(request_timeout))
        self.inactivity_timeout = max(10, int(inactivity_timeout))
        self.connect_timeout = max(5, int(connect_timeout))
        self.proxy = (proxy or "").strip() or None
        self.captcha_provider = (captcha_provider or "").strip().lower() or None
        self.captcha_api_key = (captcha_api_key or "").strip() or None

        self._session: aiohttp.ClientSession | None = None
        self._server_order = list(self.servers)
        random.shuffle(self._server_order)
        self._last_good_server: int | None = None

        self._cookie_cache_mtime: float | None = None
        self._cookie_cache_value = ""
        self._cookie_logged_missing = False

        self._plus: bool | None = None
        self._authenticated: bool | None = None
        self._subscription_checked_at = 0.0
        self.last_error: str | None = None

    # --------------------------------------------------------------- Cookies

    def cookie_header(self) -> str:
        file_header = ""
        if self.cookies_file:
            try:
                mtime = os.path.getmtime(self.cookies_file)
            except OSError:
                if not self._cookie_logged_missing:
                    logger.warning("notube-Cookie-Datei nicht gefunden: %s", self.cookies_file)
                    self._cookie_logged_missing = True
                mtime = None
            if mtime is not None:
                if mtime != self._cookie_cache_mtime:
                    try:
                        with open(self.cookies_file, "r", encoding="utf-8", errors="replace") as handle:
                            text = handle.read()
                    except OSError as exc:
                        logger.warning(
                            "notube-Cookie-Datei nicht lesbar (%s): %s", self.cookies_file, exc
                        )
                        text = ""
                    value = _cookie_header_from_pairs(_cookie_pairs_from_text(text))
                    self._cookie_cache_mtime = mtime
                    self._cookie_cache_value = value
                    self._cookie_logged_missing = False
                    if value:
                        logger.info("notube-Cookies geladen (%s).", self.cookies_file)
                    else:
                        logger.warning(
                            "notube-Cookie-Datei enthaelt keine notube.cc-Cookies: %s",
                            self.cookies_file,
                        )
                file_header = self._cookie_cache_value

        parts = [part for part in (file_header, self.raw_cookie_header) if part]
        return "; ".join(parts)

    def status(self) -> dict:
        return {
            "cookies_file": self.cookies_file,
            "cookies_exists": bool(self.cookies_file and os.path.exists(self.cookies_file)),
            "cookie_configured": bool(self.cookie_header()),
            "authenticated": self._authenticated,
            "plus": self._plus,
            "format": self.effective_format(),
            "lang": self.lang,
            "servers": len(self.servers),
            "proxy_enabled": bool(self.proxy),
            "captcha_configured": self.captcha_configured,
            "captcha_provider": self.captcha_provider if self.captcha_configured else None,
            "last_error": self.last_error,
        }

    # -------------------------------------------------------------- Lifecycle

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=8, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    def _headers(self, referer: str = "https://notube.cc/") -> dict:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Origin": "https://notube.cc",
            "Referer": referer,
        }
        cookie = self.cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    # ---------------------------------------------------------- Subscription

    def effective_format(self) -> str:
        if self.format and self.format.lower() != "auto":
            return self.format.lower()
        return "mp42k" if self._plus else "mp4hd"

    def format_for(self, url: str) -> str:
        """YouTube in bester Qualitaet, andere Quellen im sicheren MP4-Basismodus."""
        if self.format and self.format.lower() != "auto":
            return self.format.lower()
        if "youtube.com" in url or "youtu.be" in url:
            return "mp42k" if self._plus else "mp4hd"
        return "mp4"

    async def ensure_subscription(self, force: bool = False) -> bool:
        now = time.monotonic()
        if (
            not force
            and self._plus is not None
            and now - self._subscription_checked_at < _SUBSCRIPTION_TTL
        ):
            return self._plus
        session = await self._get_session()
        try:
            async with session.get(
                "https://notube.cc/include/ajax/users/check_subscription.php",
                headers=self._headers(),
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(total=20, sock_connect=self.connect_timeout),
            ) as response:
                text = await response.text()
                data = json.loads(text)
                self._plus = bool(data.get("subscribed"))
                self._authenticated = bool(
                    data.get("subscribed") or data.get("logged") or data.get("isLoggedIn")
                )
                self._subscription_checked_at = now
                if self._plus:
                    logger.info("notube: Plus-Session erkannt (Format %s).", self.effective_format())
                elif self.cookie_header():
                    logger.warning(
                        "notube: Cookie vorhanden, aber kein Plus-Abo erkannt - nutze %s.",
                        self.effective_format(),
                    )
                return self._plus
        except Exception as exc:
            self.last_error = f"Subscription-Check: {exc}"
            logger.debug("notube-Subscription-Check fehlgeschlagen: %s", exc)
            if self._plus is None:
                self._plus = False
            return self._plus

    # --------------------------------------------------------------- Request

    async def _post(
        self,
        url: str,
        data: dict,
        *,
        timeout: int | None = None,
    ) -> str:
        session = await self._get_session()
        total = self.request_timeout if timeout is None else timeout
        try:
            async with session.post(
                url,
                data=data,
                headers=self._headers(),
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(
                    total=total,
                    sock_connect=self.connect_timeout,
                    sock_read=total,
                ),
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise NotubeError(f"notube HTTP {response.status}: {text[:200]}")
                return text
        except asyncio.TimeoutError as exc:
            raise NotubeError(f"notube-Timeout nach {total}s") from exc
        except aiohttp.ClientError as exc:
            raise NotubeError(f"notube-Verbindungsfehler: {exc}") from exc

    async def _get(self, url: str, *, timeout: int = 120) -> tuple[str, str]:
        session = await self._get_session()
        try:
            async with session.get(
                url,
                headers=self._headers(),
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(
                    total=timeout,
                    sock_connect=self.connect_timeout,
                    sock_read=timeout,
                ),
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise NotubeError(f"notube HTTP {response.status}: {text[:200]}")
                return str(response.url), text
        except asyncio.TimeoutError as exc:
            raise NotubeError(f"notube-Timeout nach {timeout}s") from exc
        except aiohttp.ClientError as exc:
            raise NotubeError(f"notube-Verbindungsfehler: {exc}") from exc

    # ---------------------------------------------------------------- Servers

    async def _pick_server(self) -> int:
        candidates: list[int] = []
        if self._last_good_server is not None:
            candidates.append(self._last_good_server)
        candidates.extend(server for server in self._server_order if server not in candidates)
        for server in candidates:
            if await self._server_alive(server):
                self._last_good_server = server
                return server
        raise NotubeBusyError("Kein notube-Server erreichbar")

    async def _server_alive(self, server: int) -> bool:
        session = await self._get_session()
        try:
            async with session.get(
                f"https://s{server}.notube.cc/weight.php",
                headers=self._headers(),
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(total=10, sock_connect=self.connect_timeout),
            ) as response:
                await response.read()
                return response.status == 200
        except Exception:
            return False

    # --------------------------------------------------------------- Resolve

    async def resolve(self, url: str) -> NotubeDownload:
        await self.ensure_subscription()
        last_error: Exception | None = None
        for _attempt in range(3):
            server = await self._pick_server()
            try:
                return await self._resolve_on(server, url)
            except NotubeBusyError as exc:
                last_error = exc
                self._last_good_server = None
                logger.info("notube-Server s%s beschaeftigt, versuche anderen Server.", server)
                continue
        raise last_error or NotubeBusyError("notube-Server beschaeftigt")

    async def _recover_weight(self, server: int, url: str) -> dict:
        fmt = self.format_for(url)
        subscribed = "true" if self._plus else "false"
        raw = await self._post(
            f"https://s{server}.notube.cc/recover_weight.php",
            {
                "url": url,
                "format": fmt,
                "lang": self.lang,
                "subscribed": subscribed,
            },
            timeout=120,
        )
        try:
            info = json.loads(raw)
        except ValueError as exc:
            if _looks_like_challenge(raw):
                raise NotubeChallengeError(
                    "notube: Cloudflare-Captcha (Turnstile) erforderlich"
                ) from exc
            message = html.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()[:300]
            lowered = message.lower()
            if "plus" in lowered or "subscribed" in lowered or "abonn" in lowered:
                raise NotubePlusRequiredError(f"notube Plus erforderlich: {message}") from exc
            if "busy" in lowered or "wait" in lowered or "server" in lowered:
                raise NotubeBusyError(message) from exc
            if any(
                hint in lowered
                for hint in (
                    "invalid", "not supported", "unsupported", "unavailable",
                    "no video", "not found", "private", "removed",
                )
            ):
                raise NotubePermanentError(message or "notube: nicht unterstuetzt") from exc
            raise NotubeError(f"notube: unerwartete Antwort: {message}") from exc

        if str(info.get("VevoUSA") or "0") == "1":
            raise NotubePermanentError(
                "notube: Video ist urheberrechtlich gesperrt (VevoUSA)"
            )

        if str(info.get("VideoDuration") or "0") == "1":
            raise NotubePlusRequiredError(
                "notube: Video ist zu lang fuer den aktuellen Account (Plus erforderlich)"
            )

        if not str(info.get("token") or ""):
            raise NotubeError("notube: kein Token in recover_weight erhalten")
        return info

    async def probe(self, url: str) -> dict:
        """Leichte Vorabpruefung ohne Download/Konvertierung."""
        await self.ensure_subscription()
        last_error: Exception | None = None
        for _attempt in range(3):
            server = await self._pick_server()
            try:
                info = await self._recover_weight(server, url)
            except NotubeBusyError as exc:
                last_error = exc
                self._last_good_server = None
                continue
            title = unquote_plus(str(info.get("titre_mp4") or "")).strip()
            try:
                size = int(float(str(info.get("weight_total") or "0"))) or None
            except (TypeError, ValueError):
                size = None
            return {"title": title, "filesize": size, "format": self.format_for(url)}
        raise last_error or NotubeBusyError("notube-Server beschaeftigt")

    @property
    def captcha_configured(self) -> bool:
        return bool(self.captcha_provider and self.captcha_api_key)

    async def _resolve_on(self, server: int, url: str, allow_captcha: bool = True) -> NotubeDownload:
        fmt = self.format_for(url)
        subscribed = "true" if self._plus else "false"

        info = await self._recover_weight(server, url)
        token = str(info.get("token") or "")
        name = str(info.get("name_mp4") or "").strip() or "video.mp4"
        try:
            size = int(float(str(info.get("weight_total") or "0")))
        except (TypeError, ValueError):
            size = 0
        size = size if size > 0 else None

        raw_file = await self._post(
            f"https://s{server}.notube.cc/recover_file.php",
            {
                "url": url,
                "format": fmt,
                "name_mp4": name,
                "lang": self.lang,
                "token": token,
                "subscribed": subscribed,
                "playlist": "false",
                "adblock": "false",
            },
            timeout=self.request_timeout,
        )

        retour, file_token = self._parse_recover_file(raw_file, token)
        if retour == "challenge":
            if not allow_captcha or not self.captcha_configured:
                raise NotubeChallengeError(
                    "notube: Cloudflare-Captcha (Turnstile) erforderlich"
                )
            await self._solve_turnstile(server, raw_file, url, fmt, name, subscribed)
            return await self._resolve_on(server, url, allow_captcha=False)
        if retour == "busy":
            raise NotubeBusyError("notube-Server meldet HS")
        if retour == "limit":
            raise NotubeLimitError("notube-Download-Limit erreicht")
        if retour == "plus":
            raise NotubePlusRequiredError("notube: Download nur mit Plus verfuegbar")
        if retour != "ok":
            raise NotubeError(f"notube: recover_file: {retour}")

        is_youtube = "youtube.com" in url or "youtu.be" in url
        if not is_youtube:
            # Nicht-YouTube-Quellen muessen auf dem notube-Server konvertiert
            # werden. Das kann bei langen Videos dauern.
            await self._post(
                f"https://s{server}.notube.cc/conversion.php",
                {"token": file_token},
                timeout=self.request_timeout,
            )

        _final_url, page = await self._get(
            f"https://notube.cc/{self.lang}/download?token={file_token}",
            timeout=180,
        )
        match = _DOWNLOAD_LINK_RE.search(html.unescape(page))
        if not match:
            if "plus" in page.lower() and "download" not in page.lower():
                raise NotubePlusRequiredError("notube: Download nur mit Plus verfuegbar")
            raise NotubeError("notube: Download-Link nicht gefunden")
        download_url = match.group(0).replace("&amp;", "&")
        return NotubeDownload(
            url=download_url,
            filename=name,
            size=size,
            token=file_token,
        )

    async def _post_external(self, url: str, data: dict | None = None, json_data: dict | None = None) -> str:
        session = await self._get_session()
        try:
            async with session.post(
                url,
                data=data,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=60, sock_connect=self.connect_timeout),
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise NotubeChallengeError(
                        f"Captcha-Dienst HTTP {response.status}: {text[:200]}"
                    )
                return text
        except asyncio.TimeoutError as exc:
            raise NotubeChallengeError("Captcha-Dienst Timeout") from exc
        except aiohttp.ClientError as exc:
            raise NotubeChallengeError(f"Captcha-Dienst nicht erreichbar: {exc}") from exc

    async def _get_external(self, url: str, params: dict) -> str:
        session = await self._get_session()
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=60, sock_connect=self.connect_timeout),
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise NotubeChallengeError(
                        f"Captcha-Dienst HTTP {response.status}: {text[:200]}"
                    )
                return text
        except asyncio.TimeoutError as exc:
            raise NotubeChallengeError("Captcha-Dienst Timeout") from exc
        except aiohttp.ClientError as exc:
            raise NotubeChallengeError(f"Captcha-Dienst nicht erreichbar: {exc}") from exc

    async def _captcha_token(self, sitekey: str, pageurl: str) -> str:
        provider = (self.captcha_provider or "").lower()
        key = self.captcha_api_key or ""
        if provider in ("2captcha", "twocaptcha", "2captcha.com"):
            raw = await self._post_external(
                "https://2captcha.com/in.php",
                data={
                    "key": key,
                    "method": "turnstile",
                    "sitekey": sitekey,
                    "pageurl": pageurl,
                    "json": "1",
                },
            )
            try:
                started = json.loads(raw)
            except ValueError as exc:
                raise NotubeChallengeError(f"2Captcha: unerwartete Antwort: {raw[:200]}") from exc
            if int(started.get("status") or 0) != 1:
                raise NotubeChallengeError(f"2Captcha: {started.get('request') or raw[:200]}")
            task_id = str(started.get("request"))
            for _ in range(36):
                await asyncio.sleep(5)
                raw = await self._get_external(
                    "https://2captcha.com/res.php",
                    {
                        "key": key,
                        "action": "get",
                        "id": task_id,
                        "json": "1",
                    },
                )
                try:
                    result = json.loads(raw)
                except ValueError:
                    continue
                if int(result.get("status") or 0) == 1:
                    return str(result.get("request"))
                if str(result.get("request") or "") != "CAPCHA_NOT_READY":
                    raise NotubeChallengeError(
                        f"2Captcha: {result.get('request') or raw[:200]}"
                    )
            raise NotubeChallengeError("2Captcha: Timeout beim Loesen")

        if provider in ("capsolver", "cap-solver"):
            raw = await self._post_external(
                "https://api.capsolver.com/createTask",
                json_data={
                    "clientKey": key,
                    "task": {
                        "type": "AntiTurnstileTaskProxyLess",
                        "websiteURL": pageurl,
                        "websiteKey": sitekey,
                    },
                },
            )
            try:
                started = json.loads(raw)
            except ValueError as exc:
                raise NotubeChallengeError(f"CapSolver: unerwartete Antwort: {raw[:200]}") from exc
            if started.get("errorId"):
                raise NotubeChallengeError(
                    f"CapSolver: {started.get('errorDescription') or raw[:200]}"
                )
            task_id = started.get("taskId")
            if not task_id:
                raise NotubeChallengeError(f"CapSolver: kein taskId: {raw[:200]}")
            for _ in range(36):
                await asyncio.sleep(5)
                raw = await self._post_external(
                    "https://api.capsolver.com/getTaskResult",
                    json_data={"clientKey": key, "taskId": task_id},
                )
                try:
                    result = json.loads(raw)
                except ValueError:
                    continue
                if result.get("errorId"):
                    raise NotubeChallengeError(
                        f"CapSolver: {result.get('errorDescription') or raw[:200]}"
                    )
                if result.get("status") == "ready":
                    token = (result.get("solution") or {}).get("token")
                    if token:
                        return str(token)
                    raise NotubeChallengeError("CapSolver: kein Token in der Antwort")
            raise NotubeChallengeError("CapSolver: Timeout beim Loesen")

        raise NotubeChallengeError(
            f"Unbekannter Captcha-Provider '{self.captcha_provider}' "
            "(unterstuetzt: 2captcha, capsolver)"
        )

    async def _solve_turnstile(
        self,
        server: int,
        challenge_html: str,
        url: str,
        fmt: str,
        name: str,
        subscribed: str,
    ) -> None:
        match = _TURNSTILE_SITEKEY_RE.search(challenge_html or "")
        if not match:
            raise NotubeChallengeError(
                "notube-Captcha erkannt, aber kein data-sitekey gefunden"
            )
        sitekey = match.group(1)
        pageurl = f"https://s{server}.notube.cc/recover_file.php"
        logger.info("notube: loese Cloudflare-Turnstile ueber %s...", self.captcha_provider)
        token = await self._captcha_token(sitekey, pageurl)
        result = await self._post(
            f"https://s{server}.notube.cc/recover_file.php",
            {
                "cf-turnstile-response": token,
                "url": url,
                "format": fmt,
                "name_mp4": name,
                "subscribed": subscribed,
                "lang": self.lang,
            },
            timeout=120,
        )
        if "CaptchaOK" not in (result or ""):
            raise NotubeChallengeError(
                f"notube-Captcha wurde nicht akzeptiert: {result[:200]}"
            )
        logger.info("notube: Cloudflare-Captcha erfolgreich geloest.")

    @staticmethod
    def _parse_recover_file(raw: str, fallback_token: str) -> tuple[str, str]:
        text = (raw or "").strip()
        token = fallback_token
        retour = ""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                retour = str(data.get("retour") or data.get("status") or "").strip()
                token = str(data.get("token") or fallback_token)
            else:
                retour = str(data)
        except ValueError:
            retour = text

        if _looks_like_challenge(retour):
            return "challenge", token
        lowered = retour.lower()
        if lowered in ("ok", "1", "true"):
            return "ok", token
        if lowered in ("hs", "busy"):
            return "busy", token
        if lowered in ("exceeded", "limitation", "limit"):
            return "limit", token
        if lowered in ("", "0", "false"):
            return "error", token
        if "plus" in lowered or "subscri" in lowered:
            return "plus", token
        return retour or "error", token

    # -------------------------------------------------------------- Download

    async def download(
        self,
        job: NotubeDownload,
        out_base: str,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> str:
        final_path = out_base + ".mp4"
        part_path = final_path + ".part"
        os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
        for stale in (final_path, part_path):
            try:
                os.remove(stale)
            except FileNotFoundError:
                pass

        session = await self._get_session()
        downloaded = 0
        content_type = ""
        try:
            async with session.get(
                job.url,
                headers=self._headers(referer=f"https://notube.cc/{self.lang}/download"),
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    sock_connect=self.connect_timeout,
                    sock_read=self.inactivity_timeout,
                ),
            ) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if response.status != 200:
                    raise NotubeError(f"notube download HTTP {response.status}")
                if content_type.startswith("text/html"):
                    body = (await response.text())[:2000]
                    if _looks_like_challenge(body):
                        raise NotubeChallengeError(
                            "notube: Cloudflare-Captcha (Turnstile) erforderlich"
                        )
                    raise NotubePermanentError(
                        f"notube lieferte HTML statt Video: {body[:300]}"
                    )
                header_size = response.headers.get("Content-Length")
                total = job.size
                if header_size and header_size.isdigit():
                    total = int(header_size)
                total = total or 0

                with open(part_path, "wb") as handle:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        if cancel_check is not None:
                            cancel_check()
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback is not None:
                            # weight_total ist bei notube nur eine Schaetzung und
                            # kann kleiner als die fertige Datei sein.
                            progress_callback(downloaded, max(total, downloaded))

            if downloaded <= 0:
                raise NotubeError("notube: leere Datei erhalten")
            if job.size and downloaded < int(job.size * 0.95):
                raise NotubeError(
                    f"notube: Download unvollstaendig ({downloaded} von {job.size} Bytes)"
                )
            os.replace(part_path, final_path)
            if progress_callback is not None:
                progress_callback(downloaded, downloaded)
            return final_path
        except BaseException:
            try:
                os.remove(part_path)
            except OSError:
                pass
            raise
