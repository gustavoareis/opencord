import re

from config import sp, SPOTIFY_TRACK_RE, SPOTIFY_PLAYLIST_RE, SPOTIFY_ALBUM_RE, MAX_SPOTIFY_ITEMS


def spotify_id_from_url(url: str) -> str:
    return url.split("/")[-1].split("?")[0].strip()


def is_spotify_track_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_RE.search(url))


def is_spotify_playlist_url(url: str) -> bool:
    return bool(SPOTIFY_PLAYLIST_RE.search(url))


def is_spotify_album_url(url: str) -> bool:
    return bool(SPOTIFY_ALBUM_RE.search(url))


def spotify_track_to_query(track_obj: dict) -> tuple[str, str]:
    name = (track_obj.get("name") or "").strip()
    artists = track_obj.get("artists") or []
    artist_names = [a.get("name", "").strip() for a in artists if a.get("name")]
    artist = artist_names[0] if artist_names else ""
    q = f"{name} {artist}".strip()

    # Remove caracteres especiais que podem causar problemas no YouTube
    q = re.sub(r'[^\w\s\-\(\)]', '', q, flags=re.UNICODE)
    q = re.sub(r'\s+', ' ', q).strip()

    result = q if q else "unknown"
    display = f"{name} - {', '.join(artist_names)}" if name and artist_names else name or "unknown"
    print(f"[DEBUG] Spotify query gerada: '{result}' (nome: {name}, artista: {artist})")
    return result, display


def get_spotify_track_query(spotify_url: str) -> tuple[str, str] | None:
    try:
        track_id = spotify_id_from_url(spotify_url)
        print(f"[DEBUG] Track ID extraído: {track_id}")
        track = sp.track(track_id)
        print(f"[DEBUG] Dados do Spotify recebidos: {track.get('name')} por {[a.get('name') for a in track.get('artists', [])]}")
        return spotify_track_to_query(track)
    except Exception as e:
        print(f"Erro ao acessar Spotify (track): {e}")
        return None


def get_spotify_playlist_queries(spotify_url: str, limit: int = MAX_SPOTIFY_ITEMS) -> list[tuple[str, str]] | None:
    try:
        playlist_id = spotify_id_from_url(spotify_url)
        out: list[tuple[str, str]] = []
        offset = 0
        page_size = 100

        while len(out) < limit:
            resp = sp.playlist_items(
                playlist_id,
                limit=min(page_size, limit - len(out)),
                offset=offset,
                additional_types=("track",),
            )
            items = resp.get("items") or []
            if not items:
                break

            for it in items:
                tr = (it or {}).get("track")
                if not tr:
                    continue
                if tr.get("is_local"):
                    continue
                out.append(spotify_track_to_query(tr))
                if len(out) >= limit:
                    break

            offset += len(items)
            if not resp.get("next"):
                break

        return [(q, d) for q, d in out if q and q != "unknown"]
    except Exception as e:
        print(f"Erro ao acessar Spotify (playlist): {e}")
        return None


def get_spotify_album_queries(spotify_url: str, limit: int = MAX_SPOTIFY_ITEMS) -> list[tuple[str, str]] | None:
    try:
        album_id = spotify_id_from_url(spotify_url)
        out: list[tuple[str, str]] = []
        offset = 0
        page_size = 50

        while len(out) < limit:
            resp = sp.album_tracks(album_id, limit=min(page_size, limit - len(out)), offset=offset)
            items = resp.get("items") or []
            if not items:
                break

            for tr in items:
                if not tr:
                    continue
                out.append(spotify_track_to_query(tr))
                if len(out) >= limit:
                    break

            offset += len(items)
            if not resp.get("next"):
                break

        return [(q, d) for q, d in out if q and q != "unknown"]
    except Exception as e:
        print(f"Erro ao acessar Spotify (album): {e}")
        return None
