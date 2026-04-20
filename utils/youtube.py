import re

import yt_dlp

ytdl = yt_dlp.YoutubeDL({
    "format": "bestaudio/best",
    "quiet": True,
    "ignoreerrors": True,
    "retries": 3,
    "fragment_retries": 3,
    "extractor_retries": 3,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
})

YOUTUBE_RE = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_RE.match(text.strip()))


def is_playlist_url(url: str) -> bool:
    return "list=" in url
