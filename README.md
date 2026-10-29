# Streamrecorder VOD Uploader

Automatisiertes Video-Archiv: **n8n** liest neue Streamrecorder-Recordings aus und
uebergibt sie an einen **Telegram-Bot**, der sie herunterlaedt, bei Bedarf
aufteilt und in Telegram-Foren ablegt. Zusaetzlich archiviert der Bot Videos aus
**rss.app-Feeds** per `yt-dlp`.

> Inoffizielles Privatprojekt. Keine Verbindung zu Streamrecorder, Telegram,
> n8n, rss.app oder yt-dlp. Nutzung auf eigene Verantwortung.

## Inhalt

- [Features](#features)
- [Architektur](#architektur)
- [Voraussetzungen](#voraussetzungen)
- [Schnellstart](#schnellstart)
- [Konfiguration](#konfiguration)
- [HTTP-Endpunkte](#http-endpunkte)
- [Dashboard](#dashboard)
- [n8n-Integration](#n8n-integration)
- [Persistenter Job-State](#persistenter-job-state)
- [Betrieb](#betrieb)
- [Sicherheit](#sicherheit)
- [Rechtliches & Lizenzstatus](#rechtliches--lizenzstatus)
- [Projektstruktur](#projektstruktur)
- [Fehlersuche](#fehlersuche)
## Features

- **Streamrecorder-Uploads** per n8n: Download, optionales 1,8-GB-Splitting,
  Telegram-Upload, Weiterleitung in Forum-Topics, Markierung als `downloaded`.
- **Dynamische Zielkanäle**: Die n8n-Workflows lesen die abonnierten TargetIDs
  bei jedem Lauf live aus dem Streamrecorder-Account, statt sie zu pflegen.
- **RSS-Archiv**: rss.app-Feeds (YouTube, TikTok, X, Instagram, ...) werden per
  `yt-dlp` aufgeloest und durch dieselbe Pipeline geschickt.
- **Dashboard** mit Login, Queue, aktivem Upload, Historie, Logs, RSS-Status,
  Topic-Verwaltung und Buttons zum Starten der n8n-Workflows.
- **Persistenter Job-State**: Neustarts/Deploys verlieren keine Jobs; bereits
  hochgeladene Teile werden nach einem Abbruch uebersprungen.
- **Idempotenz**: Doppelte `/upload`-Requests (z. B. n8n-Retries) erzeugen keine
  doppelten Telegram-Nachrichten.

## Architektur

```
                    ┌──────────────────────────────┐
  Streamrecorder ──▶│  n8n (extern, nicht im Repo) │
       API          │  3 Workflows, 15-Min-Takt    │
                    └──────────────┬───────────────┘
                                   │ POST /upload (JSON)
                                   ▼
  rss.app ──▶ rss_archiver ──▶ ┌─────────────────────────────┐
                               │  vod_uploader (Container)   │
  Dashboard ◀── /voduploader ──│  aiohttp + Telethon         │
                               │  Queue / job_store          │
                               └───────┬─────────────┬───────┘
                                       │             │
                             ./state_data       Telegram API
                          (Jobs + Dateien)   (Chat + Forum-Topics)
```

- **n8n** ermittelt neue Recordings und schickt einen Job pro Datei.
- **vod_uploader** serialisiert alle Uploads, laedt herunter, splittet > 1,8 GB,
  laedt nach Telegram hoch und leitet in das passende Forum-Topic weiter.
- **state_data** haelt Queue und Fortschritt auf einem Volume fest.

## Voraussetzungen

- Docker mit Compose v2
- Telegram: `api_id`/`api_hash` von <https://my.telegram.org>, Bot-Token von
  [@BotFather](https://t.me/BotFather), Ziel-Chat und Forum-ID
- Streamrecorder-Account (Session-Cookie) fuer die Recording-Uploads
- Optional: n8n-Instanz fuer die Automatisierung
- Optional: rss.app-Feeds fuer das RSS-Archiv

## Schnellstart

```bash
git clone https://github.com/protocatzk/streamrecorder-n8n-vod-uploader.git
cd streamrecorder-n8n-vod-uploader/vod-uploader

cp .env.example .env
# .env ausfuellen: Telegram-Zugangsdaten, Chat-IDs, RSS/n8n optional

docker compose build
docker compose up -d
docker compose logs -f vod_uploader
```

Danach:

- Dashboard: `http://<host>:8080/voduploader` (Login per Telegram-Deep-Link)
- Health: `http://<host>:8080/health`

Im Beispiel-Compose laeuft der Container hinter Traefik; ohne Traefik muss ein
Port veroeffentlicht werden (z. B. `ports: ["8080:8080"]`) und die
`traefik.*`-Labels muessen entfernt werden.

## Konfiguration

Alle Einstellungen liegen in `vod-uploader/.env` (Vorlage:
`.env.example`). Die vollstaendige Liste inklusive RSS-Optionen steht in
[`vod-uploader/README.md`](vod-uploader/README.md).

Die wichtigsten Variablen:

| Variable | Bedeutung |
|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Telegram-API-Zugang (my.telegram.org) |
| `TELEGRAM_BOT_TOKEN` | Bot-Token |
| `TELEGRAM_CHAT_ID` | Ziel-Chat fuer Uploads |
| `TELEGRAM_FORUM_CHAT_ID` | Forum-Supergruppe fuer Topic-Weiterleitung |
| `ALLOWED_DASHBOARD_USERS` | Telegram-Handles/IDs fuer den Dashboard-Login |
| `PARALLEL_UPLOAD_WORKERS` | Parallele Upload-Verbindungen (Default 3) |
| `DOWNLOAD_INACTIVITY_TIMEOUT` | Abbruch bei Inaktivitaet in Sekunden |
| `RSS_ENABLED` / `RSS_FEED_URLS` | RSS-Archiv und Feeds |
| `RSS_ARCHIVE_CHAT_ID` / `RSS_ARCHIVE_FORUM_CHAT_ID` | Ziele fuer RSS-Uploads |
| `N8N_WEBHOOKS` | Webhook-URLs fuer die Dashboard-Buttons (`name=url,...`) |
| `STATE_DIR` | Pfad des Job-Spools (Default `/app/state`) |
| `JOB_DONE_TTL_DAYS` | Duplikat-Gedaechtnis in Tagen (Default 14) |
| `JOB_STALE_DAYS` | Aufraeumen verwaister Job-Verzeichnisse (Default 3) |

> `.env`, Session-Dateien, Cookies und `state_data/` sind per `.gitignore`
> ausgeschlossen und gehoeren **nicht** ins Repository.

## HTTP-Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/upload` | Job von n8n; antwortet `202 duplicate` bei bereits laufendem/erledigtem Job |
| `GET` | `/health` | Status, Queue-Laenge, RSS-Zusammenfassung |
| `POST` | `/rss/check` | RSS-Poll manuell ausloesen (`202` gestartet, `409` laeuft) |
| `POST` | `/rss/backfill?limit=10` | Die neuesten N bestehenden Videos nacharchivieren |
| `GET` | `/rss/status` | Feed-Status, Zaehler, Fehler |
| `POST` | `/n8n/run?name=<key>` | n8n-Workflow per Webhook starten (Dashboard-Session noetig) |
| `GET` | `/voduploader` | Dashboard |
| `GET` | `/voduploader/topics` | Topic-Verwaltung |

Unter dem Traefik-Prefix existieren dieselben Endpunkte zusaetzlich als
`/voduploader/...` (das Dashboard nutzt diese Variante).

## Dashboard

- **Login** per Telegram: Das Dashboard erzeugt einen Deep-Link, die Anmeldung
  wird im Bot per Inline-Button bestaetigt. Nur `ALLOWED_DASHBOARD_USERS` haben
  Zugriff.
- **Aktiver Upload / Queue / Historie / Logs** werden per Server-Sent-Events
  live aktualisiert.
- **RSS-Archiv**: Feed-Status, Zaehler und Buttons *Jetzt pruefen* /
  *10 nachholen*.
- **n8n-Workflows**: Karten mit einem Button pro Account; sichtbar, sobald
  `N8N_WEBHOOKS` konfiguriert ist.
- **Topics verwalten**: Aliase und Forum-Topic-IDs pflegen
  (`topics_cache.json`).

## n8n-Integration

Die Workflows liegen **nicht** in diesem Repository, sondern in der n8n-Instanz
(Backups separat aufbewahren). Sie bestehen pro Streamrecorder-Account aus:

1. **Schedule Trigger** (z. B. alle 15 Minuten) und optional einem
   **Webhook Trigger** fuer den Dashboard-Button.
2. **Configuration**: Session-Cookie des Accounts.
3. **Get Streamrecorder Targets**: liest `https://streamrecorder.io/userrecordings`
   und extrahiert die abonnierten TargetIDs inklusive Name und Plattform.
   (Die JSON-API `recordingsv2` kann das nicht – sie verlangt eine `targetid`.)
4. **Loop Streamers** → **Get Recordings** (`/api/user/recordingsv2`) →
   Filter auf `status=finished`, `downloaded=false` →
   **Upload to Telegram** (`POST http://vod_uploader:8080/upload`).

Dadurch werden neu abonnierte Kanaele automatisch mitgenommen, ohne die
Workflow-Datei anzupassen. Der Bot ist im selben Docker-Netz wie n8n
(`n8n_n8n-network`), damit `http://vod_uploader:8080` und
`http://n8n:5678/webhook/...` erreichbar sind.

## Persistenter Job-State

Das Volume `./state_data` (im Container `/app/state`) enthaelt:

| Datei/Ordner | Inhalt |
|---|---|
| `jobs.json` | offene Jobs mit Stage, Versuchen und Teil-Manifest |
| `done.json` | abgeschlossene Jobs fuer die Duplikat-Erkennung |
| `jobs/<key>/` | Download-Datei, Thumbnail und Split-Teile |

Ablauf bei einem Neustart:

1. Offene Jobs werden automatisch wieder aufgenommen.
2. Eine bereits vollstaendig geladene Datei wird wiederverwendet.
3. Bereits gesendete Telegram-Teile werden anhand ihrer Message-ID uebersprungen.
4. Nur der zum Abbruchzeitpunkt laufende Teil wird erneut hochgeladen.

Ein Deploy kostet damit hoechstens einen Teil, nie die ganze Queue.

## Betrieb

```bash
# Bauen und starten
docker compose build
docker compose up -d

# Logs
docker compose logs -f vod_uploader

# Status (im Container, da der Port im Beispiel nicht nach aussen zeigt)
docker compose exec vod_uploader curl -s http://127.0.0.1:8080/health

# Rollback auf das vorherige Image
docker tag vod-uploader-vod_uploader:pre-state vod-uploader-vod_uploader:latest
docker compose up -d
```

- `stop_grace_period: 30s` gibt dem Bot Zeit, den aktuellen Teil zu beenden.
- Das Volume `./state_data` sollte in Backups enthalten sein, wenn laufende Jobs
  einen Neustart ueberleben sollen.
- Fuer Wartung laesst sich der Container jederzeit stoppen; offene Jobs werden
  beim naechsten Start fortgesetzt (die n8n-Requests laufen ins Leere und werden
  beim naechsten Workflow-Lauf wiederholt).

## Sicherheit

- Das Repository enthaelt **keine** Secrets: `.env`, `*.session`,
  `topics_cache.json`, `rss_data/`, `state_data/` und Cookies sind ignoriert.
- Der Dashboard-Zugang ist an Telegram-Handles gebunden; die Session liegt nur
  im Speicher (nach einem Neustart ist ein erneuter Login noetig).
- Der Container sollte nicht ungeschuetzt im Internet stehen. Fuer oeffentliche
  Hosts empfiehlt sich ein vorgeschalteter Auth-Proxy (das Beispiel nutzt Traefik
  plus Forward-Auth fuer n8n).
- Streamrecorder-Cookies sind vollwertige Session-Token. Sie gehoeren in die
  n8n-Konfiguration, nicht in dieses Repository, und laufen regelmaessig ab.
- Bitte Rate-Limits und Nutzungsbedingungen der abgefragten Dienste beachten.

## Rechtliches & Lizenzstatus

**Dieses Projekt wird unter keiner Open-Source-Lizenz veroeffentlicht.**
Es ist oeffentlich einsehbar, aber es wird keine Erlaubnis zur Nutzung,
Vervielfaltigung, Veraenderung oder Weitergabe erteilt („all rights reserved“).
Copyright (c) 2026 protocatzk. Anfragen fuer eine Nutzung bitte ueber den
Repository-Eigentuemer.

Fremdkomponenten und ihre Lizenzen sind in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) aufgefuehrt, inklusive der
vollstaendigen Lizenztexte. Das Docker-Image enthaelt unter anderem FFmpeg
(GPL-2.0-or-later, Debian-Build), Telethon (MIT), aiohttp (Apache-2.0) und
yt-dlp (Unlicense).

**Inhaltliche Verantwortung:** Das Tool laedt Videos von Drittanbietern. Wer es
betreibt, ist selbst dafuer verantwortlich, dass die Rechte an den Inhalten
vorliegen und die Nutzungsbedingungen von Streamrecorder, Telegram, rss.app und
den jeweiligen Plattformen eingehalten werden. Es werden keine Inhalte
mitgeliefert.

## Projektstruktur

```
.
├── README.md                  # diese Datei
├── THIRD_PARTY_NOTICES.md     # Lizenzen und Hinweise Dritter
├── .gitignore
└── vod-uploader/
    ├── main.py                # aiohttp-Server, Dashboard, Upload-Pipeline
    ├── fast_uploader.py       # paralleler Telegram-Chunk-Upload (Telethon-Beispiel)
    ├── job_store.py           # persistenter Job-Spool mit Resume
    ├── rss_archiver.py        # rss.app-Polling und yt-dlp-Download
    ├── topic_manager.py       # Forum-Topics und Alias-Cache
    ├── dashboard_templates.py # HTML/CSS/JS des Dashboards
    ├── Dockerfile
    ├── docker-compose.yml
    ├── requirements.txt
    ├── README.md              # Details zu RSS, Umgebungsvariablen, Topics
    └── .env.example
```

## Fehlersuche

| Problem | Ursache / Loesung |
|---|---|
| `Keine RSS-Feeds konfiguriert` | Weder `RSS_FEED_URLS` noch OPML gesetzt bzw. `RSS_FEED_TITLES` passt nicht |
| `Streamrecorder: Login-Seite ...` | Session-Cookie im n8n-Workflow abgelaufen – Cookie erneuern |
| `401 Unauthorized` am Dashboard | Session abgelaufen (Neustart) – neu per Telegram einloggen |
| n8n-Button liefert `Nicht verfuegbar` | `N8N_WEBHOOKS` leer oder Webhook im Workflow nicht aktiv |
| `202 duplicate` im n8n-Log | Job laeuft bereits oder wurde bereits hochgeladen (gewollt) |
| Upload haengt nach Neustart | Log auf `Setze gespeicherten Job fort` pruefen; Teile mit Message-ID werden uebersprungen |
| Splitting schlaegt fehl | FFmpeg-Meldung im Log; Job-Verzeichnis in `state_data/jobs/<key>` pruefen |
