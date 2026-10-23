import asyncio
import hashlib
import inspect
import json
import logging
import os
from typing import Optional, Callable

from telethon import TelegramClient, helpers
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import SaveFilePartRequest, SaveBigFilePartRequest
from telethon.tl.types import InputFile, InputFileBig, TypeInputFile

logger = logging.getLogger('vod_uploader.fast_uploader')

class UploadSender:
    def __init__(
        self,
        client: TelegramClient,
        sender: MTProtoSender,
        file_id: int,
        part_count: int,
        big: bool,
        index: int,
        stride: int,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.client = client
        self.sender = sender
        self.part_count = part_count
        self.big = big
        self.file_id = file_id
        self.stride = stride
        self.file_part = index
        self.previous: Optional[asyncio.Task] = None
        self.loop = loop

    async def next(self, data: bytes) -> None:
        if self.previous:
            await self.previous
        self.previous = self.loop.create_task(self._next(data, self.file_part))
        self.file_part += self.stride

    async def _next(self, data: bytes, part_index: int) -> None:
        if self.big:
            req = SaveBigFilePartRequest(self.file_id, part_index, self.part_count, data)
        else:
            req = SaveFilePartRequest(self.file_id, part_index, data)
        await self.client._call(self.sender, req)

    async def disconnect(self) -> None:
        if self.previous:
            await self.previous
        return await self.sender.disconnect()


class ParallelTransferrer:
    def __init__(self, client: TelegramClient, connection_count: int = 6) -> None:
        self.client = client
        self.loop = client.loop or asyncio.get_running_loop()
        self.connection_count = max(1, connection_count)
        self.dc_id = client.session.dc_id
        self.auth_key = client.session.auth_key
        self.senders: list[UploadSender] = []
        self.upload_ticker = 0

    async def _create_sender(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        await sender.connect(
            self.client._connection(
                dc.ip_address,
                dc.port,
                dc.id,
                loggers=self.client._log,
                proxy=self.client._proxy,
            )
        )
        if not self.auth_key:
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(
                id=auth.id, bytes=auth.bytes
            )
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key
        return sender

    async def init_upload(self, file_id: int, file_size: int) -> tuple[int, int, bool]:
        part_size = 512 * 1024  # Standard Telegram MTProto Chunk-Größe (512 KB)
        part_count = (file_size + part_size - 1) // part_size
        is_large = file_size > 10 * 1024 * 1024

        actual_conns = min(self.connection_count, max(1, part_count))
        logger.info(f"Initialisiere {actual_conns} parallele MTProto-Upload-Verbindungen für {part_count} Chunks...")

        first_sender = await self._create_upload_sender(file_id, part_count, is_large, 0, actual_conns)
        other_senders = await asyncio.gather(*[
            self._create_upload_sender(file_id, part_count, is_large, i, actual_conns)
            for i in range(1, actual_conns)
        ])
        self.senders = [first_sender, *other_senders]
        self.upload_ticker = 0
        return part_size, part_count, is_large

    async def _create_upload_sender(self, file_id: int, part_count: int, big: bool, index: int, stride: int) -> UploadSender:
        sender = await self._create_sender()
        return UploadSender(self.client, sender, file_id, part_count, big, index, stride, loop=self.loop)

    async def upload(self, part: bytes) -> None:
        await self.senders[self.upload_ticker].next(part)
        self.upload_ticker = (self.upload_ticker + 1) % len(self.senders)

    async def finish_upload(self) -> None:
        if self.senders:
            await asyncio.gather(*[sender.disconnect() for sender in self.senders], return_exceptions=True)
            self.senders = []

    async def cleanup(self) -> None:
        await self.finish_upload()


async def fast_upload_file(
    client: TelegramClient,
    file_path: str,
    max_workers: int = 6,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> TypeInputFile:
    """
    Lädt eine Datei parallel in 512KB Chunks über mehrere MTProto-Verbindungen hoch.
    Gibt ein InputFileBig bzw. InputFile Objekt zurück, das direkt an client.send_file übergeben werden kann.
    """
    file_id = helpers.generate_random_long()
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    uploader = ParallelTransferrer(client, connection_count=max_workers)
    try:
        part_size, part_count, is_large = await uploader.init_upload(file_id, file_size)

        uploaded_bytes = 0
        hash_md5 = hashlib.md5() if not is_large else None

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(part_size)
                if not chunk:
                    break
                if hash_md5:
                    hash_md5.update(chunk)
                await uploader.upload(chunk)
                uploaded_bytes += len(chunk)
                if progress_callback:
                    r = progress_callback(uploaded_bytes, file_size)
                    if inspect.isawaitable(r):
                        await r

        await uploader.finish_upload()
        if progress_callback:
            r = progress_callback(file_size, file_size)
            if inspect.isawaitable(r):
                await r

        if is_large:
            return InputFileBig(file_id, part_count, file_name)
        else:
            return InputFile(file_id, part_count, file_name, hash_md5.hexdigest())
    except Exception as e:
        await uploader.cleanup()
        raise e


async def get_video_metadata(file_path: str) -> dict:
    """Extrahiert Breite, Höhe und Dauer des Videos via ffprobe für optimales Telegram-Streaming."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "json",
        file_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout.decode('utf-8'))
            width = 1280
            height = 720
            duration = 0.0

            streams = data.get("streams", [])
            if streams and isinstance(streams, list):
                s0 = streams[0]
                width = int(s0.get("width") or width)
                height = int(s0.get("height") or height)
                if s0.get("duration"):
                    try:
                        duration = float(s0["duration"])
                    except (ValueError, TypeError):
                        pass

            if duration <= 0:
                format_info = data.get("format", {})
                if format_info.get("duration"):
                    try:
                        duration = float(format_info["duration"])
                    except (ValueError, TypeError):
                        pass

            return {"width": width, "height": height, "duration": duration}
    except Exception as e:
        logger.warning(f"ffprobe Metadaten-Extraktion fehlgeschlagen für {file_path}: {e}")

    return {"width": 1280, "height": 720, "duration": 0.0}
