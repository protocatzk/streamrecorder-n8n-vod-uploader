import re
import os
import json
import shutil
import logging
from typing import Optional, Dict
from telethon import TelegramClient, helpers
from telethon.tl.functions.messages import CreateForumTopicRequest, ForwardMessagesRequest
from telethon.tl.types import MessageActionTopicCreate

logger = logging.getLogger('vod_uploader.topic_manager')

CACHE_FILE_PATH = os.getenv("TOPICS_CACHE_FILE", "topics_cache.json")

# rss.app haengt Plattform-Suffixe an Feed-Titel, z. B. "MontanaBlack - YouTube".
PLATFORM_SUFFIX_RE = re.compile(
    r"\s*(?:[-–—|/]\s*(?:youtube|twitter|x|tiktok|instagram|facebook|twitch|odysee|rumble|vimeo|kick|reddit)"
    r"(?:\s*\([^)]*\))?)\s*$",
    re.IGNORECASE,
)


def strip_platform_suffix(text: str) -> str:
    """Entfernt Endungen wie ' - YouTube' oder ' / Twitter' von Kanalnamen."""
    cleaned = PLATFORM_SUFFIX_RE.sub("", str(text or "")).strip()
    return cleaned or str(text or "").strip()


def normalize_key(text: str) -> str:
    """Entfernt Emojis, Sonderzeichen und Leerzeichen für robustes Matching."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text or '')).lower()


def _match_titles(title: str) -> list[str]:
    titles = []
    for candidate in (title.strip(), strip_platform_suffix(title)):
        if candidate and candidate not in titles:
            titles.append(candidate)
    return titles


def _coerce_chat_reference(value):
    """Wandelt numerische Chat-IDs (auch als String) in int um, lässt Usernames unverändert."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return value


class TopicManager:
    def __init__(self, cache_file: str = CACHE_FILE_PATH):
        self.cache_file = cache_file
        # Cache structure: { str(chat_id): { streamer_key: topic_id } }
        self.cache: Dict[str, Dict[str, int]] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        self.cache = json.loads(content)
                    else:
                        self.cache = {}
                total_topics = sum(len(v) for v in self.cache.values() if isinstance(v, dict))
                logger.info(f"Topic-Cache aus '{self.cache_file}' geladen: {total_topics} Topics bekannt.")
            except Exception as e:
                logger.warning(f"Konnte Topic-Cache {self.cache_file} nicht lesen: {e}")
                self.cache = {}
        else:
            self.cache = {}

    def _save_cache(self):
        try:
            temp_file = f"{self.cache_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            try:
                os.replace(temp_file, self.cache_file)
            except OSError:
                # Docker bind mount fallback: Inode cannot be replaced, copy in-place
                shutil.copyfile(temp_file, self.cache_file)
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except Exception as e:
            logger.warning(f"Konnte Topic-Cache {self.cache_file} nicht schreiben: {e}")

    def find_cached_topic(self, chat_key: str, title: str) -> Optional[int]:
        """
        Sucht mit mehrstufigem Matching nach einem passenden Thema:
        1. Exakter Match (case-insensitive), auch ohne Plattform-Suffix
        2. Bereinigter Match (ohne Emojis, Sonderzeichen, Leerzeichen)
        3. Prefix- und Substring-Match (z.B. 'montanablack88' -> 'MontanaBlack')
        Bei mehreren Treffern in Stufe 3 gewinnt der laengste Treffer.
        """
        topics_dict = self.cache.get(chat_key, {})
        if not topics_dict or not isinstance(topics_dict, dict):
            return None

        candidates = _match_titles(title)
        if not candidates:
            return None

        # 1. Exakter Match (case-insensitive)
        for candidate in candidates:
            for name, tid in topics_dict.items():
                if name.strip().lower() == candidate.lower():
                    logger.info(f"Exakter Topic-Match gefunden: '{title}' -> '{name}' (ID: {tid})")
                    return tid

        # 2. Bereinigter alphanumerischer Match (z.B. '🟣 Monte' <-> 'monte')
        for candidate in candidates:
            norm_input = normalize_key(candidate)
            if not norm_input:
                continue
            for name, tid in topics_dict.items():
                if normalize_key(name) == norm_input:
                    logger.info(f"Normalisierter Topic-Match gefunden: '{title}' -> '{name}' (ID: {tid})")
                    return tid

        # 3. Praefix- und Substring-Match (z.B. 'montanablack88' matched auf 'montanablack')
        best = None  # (score, name, tid)
        for candidate in candidates:
            norm_input = normalize_key(candidate)
            if len(norm_input) < 4:
                continue
            for name, tid in topics_dict.items():
                norm_cached = normalize_key(name)
                if len(norm_cached) < 4:
                    continue
                if norm_input.startswith(norm_cached) or norm_cached.startswith(norm_input):
                    score = min(len(norm_cached), len(norm_input))
                    if best is None or score > best[0]:
                        best = (score, name, tid, "Praefix")
                elif norm_cached in norm_input or norm_input in norm_cached:
                    score = min(len(norm_cached), len(norm_input))
                    if best is None or score > best[0]:
                        best = (score, name, tid, "Substring")

        if best:
            score, name, tid, kind = best
            logger.info(f"{kind}-Topic-Match gefunden: '{title}' <-> '{name}' (ID: {tid}, Score: {score})")
            return tid

        return None

    # ---------------------------------------------------------------- Cache-Verwaltung

    def _chat_dict(self, chat_key: str) -> Dict[str, int]:
        """Gibt das Alias-Dict eines Chats zurück und legt es bei Bedarf an."""
        chat_key = str(chat_key)
        topics = self.cache.get(chat_key)
        if not isinstance(topics, dict):
            topics = {}
            self.cache[chat_key] = topics
        return topics

    def list_topics(self, chat_key: str) -> Dict[str, int]:
        """Kopie der Alias -> Topic-ID-Zuordnung eines Chats."""
        topics = self.cache.get(str(chat_key), {})
        if not isinstance(topics, dict):
            return {}
        return {
            str(alias): tid
            for alias, tid in topics.items()
            if isinstance(tid, int) and not isinstance(tid, bool)
        }

    def add_alias(self, chat_key: str, name: str, topic_id: int) -> None:
        """Fügt einen Alias hinzu bzw. überschreibt dessen Topic-ID."""
        alias = str(name or "").strip()
        if not alias:
            raise ValueError("Alias darf nicht leer sein.")
        topic_id = int(topic_id)
        if topic_id <= 0:
            raise ValueError("Topic-ID muss eine positive Ganzzahl sein.")
        self._chat_dict(chat_key)[alias] = topic_id
        self._save_cache()

    def remove_alias(self, chat_key: str, name: str) -> bool:
        """Entfernt einen Alias. True, wenn er vorhanden war."""
        topics = self.cache.get(str(chat_key), {})
        if not isinstance(topics, dict):
            return False
        alias = str(name or "").strip()
        if alias not in topics:
            return False
        del topics[alias]
        self._save_cache()
        return True

    def remap_topic(self, chat_key: str, old_topic_id: int, new_topic_id: int) -> int:
        """Schreibt alle Aliase einer Topic-ID auf eine neue ID um."""
        topics = self.cache.get(str(chat_key))
        if not isinstance(topics, dict):
            return 0
        old_topic_id = int(old_topic_id)
        new_topic_id = int(new_topic_id)
        changed = 0
        for alias, tid in list(topics.items()):
            if tid == old_topic_id:
                topics[alias] = new_topic_id
                changed += 1
        if changed:
            self._save_cache()
        return changed

    def delete_topic(self, chat_key: str, topic_id: int) -> int:
        """Entfernt alle Aliase einer Topic-ID."""
        topics = self.cache.get(str(chat_key))
        if not isinstance(topics, dict):
            return 0
        topic_id = int(topic_id)
        removed = [alias for alias, tid in topics.items() if tid == topic_id]
        for alias in removed:
            del topics[alias]
        if removed:
            self._save_cache()
        return len(removed)

    # ---------------------------------------------------------------- Telegram

    async def _create_forum_topic(
        self,
        client: TelegramClient,
        forum_chat_id: int | str,
        title: str,
        icon_color: Optional[int] = None
    ) -> int:
        """Legt ein neues Forum-Topic an und gibt dessen ID zurück (ohne Cache-Änderung)."""
        try:
            peer = await client.get_input_entity(_coerce_chat_reference(forum_chat_id))
        except Exception as e:
            logger.error(f"Konnte Entity für Forum {forum_chat_id} nicht auflösen: {e}")
            raise

        # Telegram Topic-Titel ist auf 128 Zeichen begrenzt
        clean_title = str(title or "").strip()[:128] or "Allgemein"
        random_id = helpers.generate_random_long()

        result = await client(CreateForumTopicRequest(
            peer=peer,
            title=clean_title,
            icon_color=icon_color,
            random_id=random_id
        ))

        # Topic ID aus dem Rückgabe-Updates-Objekt ermitteln
        topic_id = None
        for update in getattr(result, "updates", []):
            msg = getattr(update, "message", None)
            if msg and isinstance(getattr(msg, "action", None), MessageActionTopicCreate):
                topic_id = msg.id
                break

        if not topic_id:
            # Fallback: Nach Service-Message oder Update mit ID suchen
            for update in getattr(result, "updates", []):
                msg = getattr(update, "message", None)
                if msg and getattr(msg, "id", None):
                    topic_id = msg.id
                    break

        if not topic_id:
            raise RuntimeError(f"Konnte Topic-ID für '{clean_title}' aus Telegram-Antwort nicht ermitteln.")

        logger.info(f"Neues Forum-Topic '{clean_title}' erfolgreich erstellt mit ID {topic_id}.")
        return topic_id

    async def create_topic(
        self,
        client: TelegramClient,
        forum_chat_id: int | str,
        title: str,
        icon_color: Optional[int] = None
    ) -> int:
        """Erstellt bewusst ein neues Forum-Topic und mappt den Titel darauf."""
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("Topic-Name darf nicht leer sein.")
        topic_id = await self._create_forum_topic(
            client, forum_chat_id, normalized_title, icon_color
        )
        self.add_alias(str(forum_chat_id), normalized_title, topic_id)
        return topic_id

    async def get_or_create_topic(
        self,
        client: TelegramClient,
        forum_chat_id: int | str,
        title: str,
        icon_color: Optional[int] = None
    ) -> int:
        """
        Sucht die Topic-ID für den angegebenen Titel im Cache per Smart-Matching.
        Falls nicht vorhanden, wird ein neues Forum-Topic in der Supergruppe erstellt
        und die ID im Cache persistent gesichert.
        """
        chat_key = str(forum_chat_id)
        if chat_key not in self.cache or not isinstance(self.cache[chat_key], dict):
            self.cache[chat_key] = {}

        normalized_title = title.strip()
        lookup_key = normalized_title.lower()

        # 1. Smart-Matching im lokalen Cache
        matched_topic_id = self.find_cached_topic(chat_key, normalized_title)
        if matched_topic_id:
            # Schnelleres Wiederfinden für die Zukunft: Alias eintragen
            if lookup_key not in self.cache[chat_key]:
                self.cache[chat_key][lookup_key] = matched_topic_id
                self._save_cache()
            return matched_topic_id

        # 2. Neues Topic anlegen
        logger.info(f"Topic '{normalized_title}' nicht im Cache. Erstelle neues Forum-Topic in Chat {forum_chat_id}...")
        topic_id = await self._create_forum_topic(
            client, forum_chat_id, normalized_title, icon_color
        )

        self.cache[chat_key][lookup_key] = topic_id
        if lookup_key.startswith('@'):
            self.cache[chat_key][lookup_key[1:]] = topic_id
        stripped_key = strip_platform_suffix(normalized_title).strip().lower()
        if stripped_key and stripped_key != lookup_key:
            self.cache[chat_key][stripped_key] = topic_id
        self._save_cache()
        return topic_id

    async def forward_messages_to_topic(
        self,
        client: TelegramClient,
        from_chat: int | str,
        to_forum_chat: int | str,
        message_ids: list[int],
        topic_id: int,
        drop_author: bool = True
    ) -> list[int]:
        """
        Leitet Nachrichten serverseitig in ein spezifisches Topic weiter.
        Verwendet top_msg_id für die Topic-Zuordnung und drop_author für saubere Posts.
        """
        if not message_ids:
            return []

        logger.info(
            f"Leite {len(message_ids)} Nachricht(en) ({message_ids}) aus Chat {from_chat} "
            f"nach Forum {to_forum_chat} in Topic {topic_id} weiter (drop_author={drop_author})..."
        )

        from_peer = await client.get_input_entity(from_chat)
        to_peer = await client.get_input_entity(to_forum_chat)
        random_ids = [helpers.generate_random_long() for _ in message_ids]

        result = await client(ForwardMessagesRequest(
            from_peer=from_peer,
            id=message_ids,
            to_peer=to_peer,
            top_msg_id=topic_id,
            drop_author=drop_author,
            random_id=random_ids
        ))

        forwarded_ids = []
        for u in getattr(result, "updates", []):
            msg = getattr(u, "message", None)
            if msg and hasattr(msg, "id"):
                forwarded_ids.append(msg.id)

        logger.info(f"Nachrichten erfolgreich in Topic {topic_id} weitergeleitet. Neue IDs: {forwarded_ids or 'OK'}")
        return forwarded_ids


topic_manager = TopicManager()
