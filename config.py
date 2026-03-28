import os
import re

import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    )
)

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl_format_options = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "default_search": "ytsearch",
    "ignoreerrors": True,
    "retries": 3,
    "fragment_retries": 3,
    "extractor_retries": 3,
    "sleep_interval": 1,
    "max_sleep_interval": 3,

    "js_runtimes": {
        "node": {}
    },

    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
        }
    },

    "remote_components": ["ejs:github"],
}

ytdl_request_gap = float(os.getenv("YTDL_REQUEST_GAP", "2.0"))
ytdl_request_jitter = float(os.getenv("YTDL_REQUEST_JITTER", "1.0"))
ytdl_max_retries = int(os.getenv("YTDL_MAX_RETRIES", "3"))
ytdl_backoff_base = float(os.getenv("YTDL_BACKOFF_BASE", "2.0"))
ytdl_backoff_jitter = float(os.getenv("YTDL_BACKOFF_JITTER", "0.5"))

ytdl_format_options["retries"] = ytdl_max_retries
ytdl_format_options["fragment_retries"] = ytdl_max_retries
ytdl_format_options["extractor_retries"] = ytdl_max_retries

player_clients_env = os.getenv("YTDL_PLAYER_CLIENTS") or os.getenv("YTDL_PLAYER_CLIENT") or ""
player_clients = [c.strip() for c in re.split(r"[,\s]+", player_clients_env) if c.strip()]
po_token = (os.getenv("YTDL_PO_TOKEN") or "").strip()

if player_clients or po_token:
    extractor_args: dict[str, dict] = {"youtube": {}}
    if player_clients:
        extractor_args["youtube"]["player_client"] = player_clients
    if po_token:
        extractor_args["youtube"]["po_token"] = po_token
    ytdl_format_options["extractor_args"] = extractor_args

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

YOUTUBE_URL_RE = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)
SPOTIFY_TRACK_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?track/", re.IGNORECASE)
SPOTIFY_PLAYLIST_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?playlist/", re.IGNORECASE)
SPOTIFY_ALBUM_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?album/", re.IGNORECASE)

MAX_SPOTIFY_ITEMS = 100
