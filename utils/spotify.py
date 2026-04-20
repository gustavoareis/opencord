import os
import re

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config import MAX_PLAYLIST_ITEMS

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
))

SPOTIFY_TRACK_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?track/", re.IGNORECASE)
SPOTIFY_PLAYLIST_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?playlist/", re.IGNORECASE)
SPOTIFY_ALBUM_RE = re.compile(r"open\.spotify\.com/(?:[\w-]+/)?album/", re.IGNORECASE)


def _spotify_id(url: str) -> str:
    return url.split("/")[-1].split("?")[0]


def _track_to_query(track: dict) -> tuple[str, str]:
    name = (track.get("name") or "").strip()
    artists = [a["name"].strip() for a in (track.get("artists") or []) if a.get("name")]
    query = f"{name} {artists[0]}".strip() if artists else name
    display = f"{name} - {', '.join(artists)}" if name and artists else name
    return query or "unknown", display or "unknown"


def _paginate_tracks(fetch_fn, extract_fn, limit: int) -> list[tuple[str, str]]:
    out, offset = [], 0
    while len(out) < limit:
        resp = fetch_fn(offset, limit - len(out))
        items = resp.get("items") or []
        if not items:
            break
        for item in items:
            track = extract_fn(item)
            if track:
                q, d = _track_to_query(track)
                if q != "unknown":
                    out.append((q, d))
            if len(out) >= limit:
                break
        offset += len(items)
        if not resp.get("next"):
            break
    return out


def is_spotify_track_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_RE.search(url))


def is_spotify_playlist_url(url: str) -> bool:
    return bool(SPOTIFY_PLAYLIST_RE.search(url))


def is_spotify_album_url(url: str) -> bool:
    return bool(SPOTIFY_ALBUM_RE.search(url))


def get_spotify_track_query(url: str) -> tuple[str, str] | None:
    try:
        return _track_to_query(sp.track(_spotify_id(url)))
    except Exception:
        return None


def get_spotify_playlist_queries(url: str, limit: int = MAX_PLAYLIST_ITEMS) -> list[tuple[str, str]]:
    sid = _spotify_id(url)
    try:
        return _paginate_tracks(
            lambda offset, remaining: sp.playlist_items(sid, limit=min(100, remaining), offset=offset, additional_types=("track",)),
            lambda item: track if (track := (item or {}).get("track")) and not track.get("is_local") else None,
            limit,
        )
    except Exception:
        return []


def get_spotify_album_queries(url: str, limit: int = MAX_PLAYLIST_ITEMS) -> list[tuple[str, str]]:
    sid = _spotify_id(url)
    try:
        return _paginate_tracks(
            lambda offset, remaining: sp.album_tracks(sid, limit=min(50, remaining), offset=offset),
            lambda item: item,
            limit,
        )
    except Exception:
        return []
