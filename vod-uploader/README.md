# Ripper VOD Uploader

Telegram-Archiv fuer Streamrecorder-VODs (per n8n) und fuer rss.app-Feeds.

## Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/upload` | Job von n8n (Streamrecorder-VOD) |
| `GET` | `/health` | Status inkl. RSS-Zusammenfassung |
| `POST` | `/rss/check` | RSS-Poll manuell ausloesen (`202` gestartet, `409` laeuft bereits) |
| `POST` | `/rss/backfill?limit=10` | Einmalig die neuesten N bestehenden Videos nacharchivieren |
| `GET` | `/rss/status` | RSS-Feeds, Zaehler, letzter Lauf, Fehler |
| `POST` | `/n8n/run?name=<key>` | n8n-Workflow per Webhook starten (Dashboard-Session noetig) |
| `GET` | `/voduploader` | Dashboard |
| `GET` | `/voduploader/topics` | Topic-Verwaltung (Tabelle) |

Unter dem Traefik-Prefix sind dieselben RSS-Endpunkte zusaetzlich als
`/voduploader/rss/check`, `/voduploader/rss/backfill` und
`/voduploader/rss/status` erreichbar (das Dashboard nutzt diese Variante).

## Topic-Verwaltung

Unter `/voduploader/topics` lassen sich die Telegram-Forum-Zuordnungen aus
`topics_cache.json` verwalten (Login wie beim Dashboard):

- Topics werden nach Topic-ID gruppiert als Tabelle angezeigt.
- **Hinzufuegen:** Name/Alias mit bestehender Topic-ID verknuepfen oder per
  Checkbox ein neues Forum-Topic im konfigurierten `TELEGRAM_FORUM_CHAT_ID`
  erstellen lassen.
- **Bearbeiten:** Topic-ID einer Gruppe aendern (gilt fuer alle Aliase) und
  Aliase hinzufuegen/entfernen.
- **Loeschen:** entfernt alle Aliase einer Topic-ID. Beim naechsten Upload kann
  dadurch ein neues Telegram-Topic entstehen.

Die Seite schreibt direkt in `topics_cache.json`; das Dateiformat bleibt
unveraendert. API-Endpunkte (alle mit Dashboard-Session):

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/voduploader/api/topics?chat_id=` | Gruppen, Aliase und Chat-Liste |
| `POST` | `/voduploader/api/topics` | Name + `topic_id` oder `create: true` |
| `PATCH` | `/voduploader/api/topics` | `topic_id` -> `new_topic_id` umschreiben |
| `DELETE` | `/voduploader/api/topics?chat_id=&topic_id=` | Gruppe loeschen |
| `POST` | `/voduploader/api/topics/alias` | Alias zu bestehender ID hinzufuegen |
| `DELETE` | `/voduploader/api/topics/alias?chat_id=&name=` | Einzelnen Alias entfernen |

## rss.app-Archiv

rss.app liefert in den Feeds nur Post-/Watch-URLs und Thumbnails, keine Videodateien.
Der Bot loest die eigentliche Datei deshalb per `yt-dlp` auf (YouTube, X, TikTok,
Instagram, Odysee, Rumble, ...) und nutzt danach die bestehende Pipeline:
Download, 1,8-GB-Split, Telegram-Upload, Forum-Topic.

### 1. OPML exportieren

In rss.app: Profilbild -> **Export** -> **OPML**. Die Datei als
`rss-app-opml.xml` in das Projekt-Root legen (neben `vod-uploader/`).

Der Bot liest die Datei bei jedem Poll neu. Neue/entfernte Feeds werden also
durch einen erneuten Export uebernommen, ohne Rebuild.

**Alternative ohne OPML:** Den direkten Feed-Link aus rss.app in
`RSS_FEED_URLS` eintragen. Dann werden `RSS_OPML_FILE` und
`RSS_FEED_TITLES` nicht benoetigt (siehe Feed-Auswahl).

### 2. Feed-Auswahl

**Mit OPML:**

```env
RSS_FEED_TITLES=Gangstolking
```

Nur Top-Level-Feeds aus der OPML werden gepollt. Unterfeeds eines Bundles werden
nicht separat abgefragt, weil das Bundle sie bereits enthaelt. `RSS_FEED_TITLES`
leer lassen, um alle Top-Level-Feeds zu verwenden.

**Ohne OPML (direkter Feed-Link):**

```env
RSS_OPML_FILE=
RSS_FEED_TITLES=
RSS_FEED_URLS=https://rss.app/feeds/xxxxxxxxxxxxxxxx.xml
```

`RSS_FEED_URLS` nimmt eine oder mehrere Feed-URLs auf (kommagetrennt). Das ist
besonders praktisch fuer ein einzelnes Bundle wie `Gangstolking`, weil kein
erneuter OPML-Export und kein Datei-Mount mehr noetig sind.

Bei Bundles nutzt der Bot `<dc:creator>` des Items als Kanalnamen. Dadurch landet
z. B. ein Video von `kettengulasch7` im bestehenden Topic `kettengulasch7`, auch
wenn es ueber das Bundle `Gangstolking` gefunden wurde.

### 3. Topic-Zuordnung

- Ziel ist `TELEGRAM_FORUM_CHAT_ID`.
- Plattform-Suffixe wie ` - YouTube` oder ` / Twitter` werden entfernt.
- Exakter, normalisierter und Substring-Match; bei mehreren Treffern gewinnt der
  laengste Treffer (siehe `topic_manager.py`).
- Kein Treffer: neues Topic im selben Forum.

### 4. Wichtige Env-Variablen

| Variable | Default | Bedeutung |
|---|---|---|
| `RSS_ENABLED` | `true` | Archiv aktivieren |
| `RSS_OPML_FILE` | `rss-app-opml.xml` | Pfad im Container; leer = keine OPML |
| `RSS_FEED_TITLES` | leer | Komma-Liste der OPML-Titel |
| `RSS_FEED_URLS` | leer | Direkte Feed-URLs (kommagetrennt), auch ohne OPML |
| `RSS_STATE_FILE` | `rss_data/rss_state.json` | Dedup-State |
| `RSS_POLL_INTERVAL_SECONDS` | `900` | 15 Minuten (Developer-Plan) |
| `RSS_INITIAL_BACKFILL` | `false` | Erstlauf nur als Baseline |
| `RSS_MAX_ITEM_AGE_HOURS` | `48` | Schutz vor Massen-Backfill |
| `RSS_MAX_ITEMS_PER_POLL` | `10` | Rest folgt im naechsten Lauf |
| `RSS_MAX_RETRIES` | `0` | `0` = unbegrenzt; sonst nach N Versuchen `failed` |
| `RSS_RETRY_BASE_SECONDS` | `900` | Erste Pause vor einem Retry |
| `RSS_RETRY_MAX_DELAY_SECONDS` | `21600` | Maximales Backoff (6 h) |
| `RSS_LIVE_RECHECK_SECONDS` | `900` | Erneute Pruefung von Live/Premiere |
| `RSS_ALLOW_LIVE` | `false` | `true` = waehrend Live aufnehmen; `false` = nach Ende nachholen |
| `RSS_TOPIC_PER_FEED` | `true` | Topic pro Quellkanal |
| `RSS_ARCHIVE_CHAT_ID` | leer | Default: `TELEGRAM_CHAT_ID` |
| `RSS_ARCHIVE_FORUM_CHAT_ID` | leer | Default: `TELEGRAM_FORUM_CHAT_ID` |
| `YTDLP_COOKIES_FILE` | leer | Netscape-Cookies fuer Login-Pflicht |
| `YTDLP_CONCURRENT_FRAGMENTS` | `4` | Parallele yt-dlp-Fragmente |
| `YTDLP_RETRIES` | `10` | yt-dlp-Retries fuer Downloads |
| `YTDLP_HTTP_CHUNK_SIZE` | `10485760` | HTTP-Chunk-Groesse in Bytes |
| `YTDLP_FORMAT` | leer | Optionales Format-Limit, z. B. 1080p |
| `DOWNLOAD_CHUNK_SIZE` | `1048576` | Chunk-Groesse des direkten Downloaders |

Der Erstlauf markiert die aktuell vorhandenen Items nur als gesehen. Ab dem
naechsten Poll werden neue Videos archiviert. Mit `RSS_INITIAL_BACKFILL=true`
wird stattdessen der komplette Feed verarbeitet.

### Bestehende Videos nacharchivieren

Einmalig die neuesten N bereits vorhandenen Videos archivieren:

```bash
curl -X POST "http://<host>:8080/rss/backfill?limit=10"
```

Das Limit ist auf 1-50 begrenzt. Die restlichen bestehenden Items bleiben
dauerhaft als gesehen markiert, ein erneuter Aufruf holt die naechsten N.
Im Dashboard gibt es dafuer den Button **10 nachholen**.

### Retries und Livestreams

Fehlgeschlagene Downloads werden nicht mehr nach zwei Versuchen verworfen.
Standardmaessig (`RSS_MAX_RETRIES=0`) laufen sie unbegrenzt weiter, mit
exponentiellem Backoff von 15 Minuten bis maximal 6 Stunden. Echte Dauerfehler
(kein Video, privat, geloescht, entfernt) werden weiterhin uebersprungen.

Livestreams, Premieren und angekuendigte Streams bleiben als `live` in der
Warteschlange. Sobald der Stream beendet und als VOD verfuegbar ist, wird er
automatisch heruntergeladen. Mit `RSS_ALLOW_LIVE=true` wird stattdessen schon
waehrend des Streams aufgenommen. Wartende Items werden auch dann weiter
verfolgt, wenn sie inzwischen aus dem RSS-Feed gefallen sind.

### Downloadgeschwindigkeit

`YTDLP_CONCURRENT_FRAGMENTS` laedt mehrere Fragmente gleichzeitig und bringt bei
YouTube/DASH/HLS den groessten Geschwindigkeitsgewinn. `YTDLP_FORMAT` kann
zusaetzlich die Aufloesung begrenzen, wenn maximale Qualitaet nicht noetig ist:

```env
YTDLP_FORMAT=bestvideo[height<=1080]+bestaudio/best
```

### 5. Cookies (optional)

X/Twitter und manche YouTube-Videos verlangen Login. Netscape-Cookies als
`vod-uploader/ytdlp/cookies.txt` ablegen, in `docker-compose.yml` den
kommentierten Mount aktivieren und setzen:

```env
YTDLP_COOKIES_FILE=/app/ytdlp/cookies.txt
```

### 6. Start

```bash
cd vod-uploader
docker compose build
docker compose up -d
docker compose logs -f vod_uploader
```

Der OPML-Mount ist optional und in `docker-compose.yml` standardmaessig
auskommentiert. Bei Nutzung von `RSS_FEED_URLS` wird keine OPML-Datei benoetigt.
`RSS_STATE_FILE` liegt im Volume `./rss_data` und ueberlebt Neustarts.

## n8n-Workflows aus dem Dashboard starten

Die n8n-Workflows (`Streamrecorder Auto-Downloader - … (API-Targets)`) haben
zusaetzlich zum Schedule Trigger einen Webhook-Trigger. Das Dashboard zeigt
dafuer drei Buttons (`Karbfen`, `Karpfen`, `Ripper`) neben **Jetzt prüfen**.
Die Buttons erscheinen nur, wenn `N8N_WEBHOOKS` gesetzt ist.

```env
N8N_WEBHOOKS=karbfenchieff=http://n8n:5678/webhook/vod-karbfenchieff,karpfenchieff=http://n8n:5678/webhook/vod-karpfenchieff,ripperchieff=http://n8n:5678/webhook/vod-ripperchieff
N8N_WEBHOOK_TIMEOUT=10
N8N_TRIGGER_COOLDOWN=10
```

- Der Aufruf `POST /voduploader/n8n/run?name=<key>` braucht eine
  Dashboard-Session; ohne `name` werden alle konfigurierten Workflows gestartet.
- Der Webhook antwortet sofort (`202`); der Workflow laeuft danach
  asynchron in n8n weiter.
- `N8N_TRIGGER_COOLDOWN` verhindert Doppelklicks. Ein manueller Start waehrend
  eines laufenden 15-Minuten-Jobs kann Videos doppelt an den Uploader schicken,
  weil sie erst nach erfolgreichem Upload als `downloaded` markiert werden.

## Persistenter Job-State

Angenommene Jobs liegen inklusive Fortschritt unter `./state_data` (im Container
`/app/state`) und ueberleben Neustarts und Deploys:

- `jobs.json`: offene Jobs mit Stage (`queued`, `downloading`, `uploading`, ...).
- `done.json`: abgeschlossene Jobs fuer die Duplikat-Erkennung (`JOB_DONE_TTL_DAYS`, Standard 14).
- `jobs/<key>/`: Download-Datei und fertige Split-Teile.

Beim Start werden offene Jobs automatisch fortgesetzt. Bereits gesendete
Telegram-Teile werden anhand ihrer Message-ID uebersprungen; ein Neustart kostet
hoechstens den gerade laufenden Teil. Doppelte `/upload`-Requests (z. B. ein
n8n-Retry nach einem Neustart) liefern `202 duplicate` statt eines zweiten
Uploads. Verwaiste Job-Verzeichnisse werden nach `JOB_STALE_DAYS` entfernt.

## Fehlersuche

- `Keine RSS-Feeds konfiguriert`: Weder `RSS_FEED_URLS` noch eine OPML ist
  gesetzt, oder `RSS_FEED_TITLES` passt auf keinen OPML-Titel. Das Dashboard
  zeigt die geladenen Feed-Titel und den OPML-Status.
- `Feed nicht lesbar`: rss.app liefert die XML-Datei nicht. Feed im rss.app
  Dashboard oeffnen und den XML-Link pruefen.
- yt-dlp-Fehler: Im Container sind `ffmpeg` und `deno` installiert; yt-dlp laedt
  den YouTube-Challenge-Solver bei Bedarf von GitHub (`ejs:github`).
- Nichts wird nach dem Erstlauf archiviert: Der Erstlauf ist absichtlich eine
  Baseline. Neues Video posten und `POST /rss/check` ausloesen.
