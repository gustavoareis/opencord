import re
import asyncio
import time
import random
from urllib.parse import urlparse, parse_qs

import discord

from config import (
    ytdl, ffmpeg_options, YOUTUBE_URL_RE,
    ytdl_request_gap, ytdl_request_jitter,
    ytdl_max_retries, ytdl_backoff_base, ytdl_backoff_jitter,
)

_ytdl_lock = asyncio.Lock()
_ytdl_next_allowed = 0.0


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_URL_RE.match(text.strip()))


def make_watch_url_from_entry(entry: dict) -> str | None:
    if not entry:
        return None

    if entry.get("webpage_url"):
        return entry["webpage_url"]

    url = entry.get("url")
    if not url:
        return None

    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", url):
        return f"https://www.youtube.com/watch?v={url}"

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return None


def looks_like_playlist_url(url: str) -> bool:
    try:
        u = url.strip()
        if "list=" in u:
            return True
        parsed = urlparse(u)
        qs = parse_qs(parsed.query)
        return "list" in qs
    except Exception:
        return False


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title") or "Sem título"
        self.webpage_url = data.get("webpage_url")
        self.stream_url = data.get("url")

    @staticmethod
    async def extract_info(query: str, *, loop: asyncio.AbstractEventLoop | None = None) -> dict:
        global _ytdl_next_allowed
        loop = loop or asyncio.get_running_loop()

        def _extract():
            return ytdl.extract_info(query, download=False)

        async with _ytdl_lock:
            now = time.monotonic()
            if now < _ytdl_next_allowed:
                await asyncio.sleep(_ytdl_next_allowed - now)

            data = None
            last_err = None
            for attempt in range(1, max(1, ytdl_max_retries) + 1):
                try:
                    data = await loop.run_in_executor(None, _extract)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    msg = str(e).lower()
                    transient = any(
                        s in msg
                        for s in (
                            "rate-limited",
                            "try again later",
                            "http error 403",
                            "http error 429",
                            "http error 503",
                            "temporarily",
                            "timeout",
                            "timed out",
                        )
                    )
                    if attempt >= ytdl_max_retries or not transient:
                        break
                    backoff = (ytdl_backoff_base ** (attempt - 1)) + random.uniform(
                        0, ytdl_backoff_jitter
                    )
                    await asyncio.sleep(backoff)

            gap = max(0.0, ytdl_request_gap + random.uniform(0, ytdl_request_jitter))
            _ytdl_next_allowed = time.monotonic() + gap

        if last_err is not None and data is None:
            raise last_err
        if not data:
            raise ValueError("Falha ao extrair informações do YouTube.")
        return data

    @classmethod
    async def from_data(cls, data: dict):
        stream_url = data.get("url")
        if not stream_url:
            raise ValueError("Não foi possível obter a URL de áudio.")
        return cls(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options), data=data)
