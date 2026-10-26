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


def normalize_key(text: str) -> str:
    """Entfernt Emojis, Sonderzeichen und Leerzeichen für robustes Matching."""
    return re.sub(r'[^a-zA-Z0-9]', '', str(text or '')).lower()


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
        1. Exakter Match (case-insensitive)
        2. Bereinigter Match (ohne Emojis, Sonderzeichen, Leerzeichen)
        3. Prefix- und Substring-Match (z.B. 'montanablack88' -> 'MontanaBlack')
        """
        topics_dict = self.cache.get(chat_key, {})
        if not topics_dict or not isinstance(topics_dict, dict):
            return None

        clean_input = title.strip()
        norm_input = normalize_key(clean_input)
        if not norm_input:
            return None

        # 1. Exakter Match (case-insensitive)
        for name, tid in topics_dict.items():
            if name.strip().lower() == clean_input.lower():
                logger.info(f"Exakter Topic-Match gefunden: '{title}' -> '{name}' (ID: {tid})")
                return tid

        # 2. Bereinigter alphanumerischer Match (z.B. '🟣 Monte' <-> 'monte')
        for name, tid in topics_dict.items():
            if normalize_key(name) == norm_input:
                logger.info(f"Normalisierter Topic-Match gefunden: '{title}' -> '{name}' (ID: {tid})")
                return tid

        # 3. Präfix- und Substring-Match (z.B. 'montanablack88' matched auf 'montanablack')
        if len(norm_input) >= 4:
            for name, tid in topics_dict.items():
                norm_cached = normalize_key(name)
                if len(norm_cached) >= 4:
                    if norm_input.startswith(norm_cached) or norm_cached.startswith(norm_input):
                        logger.info(f"Präfix-Topic-Match gefunden: '{title}' <-> '{name}' (ID: {tid})")
                        return tid
                    if norm_cached in norm_input or norm_input in norm_cached:
                        logger.info(f"Substring-Topic-Match gefunden: '{title}' <-> '{name}' (ID: {tid})")
                        return tid

        return None

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
        try:
            peer = await client.get_input_entity(forum_chat_id)
        except Exception as e:
            logger.error(f"Konnte Entity für Forum {forum_chat_id} nicht auflösen: {e}")
            raise

        # Telegram Topic-Titel ist auf 128 Zeichen begrenzt
        clean_title = normalized_title[:128] if normalized_title else "Allgemein"
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
        self.cache[chat_key][lookup_key] = topic_id
        if lookup_key.startswith('@'):
            self.cache[chat_key][lookup_key[1:]] = topic_id
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
