import os
import re
import asyncio
import random
import time
from collections import deque
from urllib.parse import urlparse, parse_qs

import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

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

    "remote_components": "ejs:github",
}

ytdl_request_gap = float(os.getenv("YTDL_REQUEST_GAP", "2.0"))
ytdl_request_jitter = float(os.getenv("YTDL_REQUEST_JITTER", "1.0"))
ytdl_max_retries = int(os.getenv("YTDL_MAX_RETRIES", "3"))
ytdl_backoff_base = float(os.getenv("YTDL_BACKOFF_BASE", "2.0"))
ytdl_backoff_jitter = float(os.getenv("YTDL_BACKOFF_JITTER", "0.5"))

ytdl_format_options["retries"] = ytdl_max_retries
ytdl_format_options["fragment_retries"] = ytdl_max_retries
ytdl_format_options["extractor_retries"] = ytdl_max_retries

_ytdl_lock = asyncio.Lock()
_ytdl_next_allowed = 0.0

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

guild_queues: dict[int, deque] = {}
guild_now_playing: dict[int, dict] = {}
guild_locks: dict[int, asyncio.Lock] = {}


def get_queue(guild_id: int) -> deque:
    if guild_id not in guild_queues:
        guild_queues[guild_id] = deque()
    return guild_queues[guild_id]


def get_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in guild_locks:
        guild_locks[guild_id] = asyncio.Lock()
    return guild_locks[guild_id]


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_URL_RE.match(text.strip()))


def spotify_id_from_url(url: str) -> str:
    return url.split("/")[-1].split("?")[0].strip()


def is_spotify_track_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_RE.search(url))


def is_spotify_playlist_url(url: str) -> bool:
    return bool(SPOTIFY_PLAYLIST_RE.search(url))


def is_spotify_album_url(url: str) -> bool:
    return bool(SPOTIFY_ALBUM_RE.search(url))


def spotify_track_to_query(track_obj: dict) -> str:
    name = (track_obj.get("name") or "").strip()
    artists = track_obj.get("artists") or []
    artist = (artists[0].get("name") or "").strip() if artists else ""
    q = f"{name} {artist}".strip()
    
    # Remove caracteres especiais que podem causar problemas no YouTube
    q = re.sub(r'[^\w\s\-\(\)]', '', q, flags=re.UNICODE)
    q = re.sub(r'\s+', ' ', q).strip()
    
    result = q if q else "unknown"
    print(f"[DEBUG] Spotify query gerada: '{result}' (nome: {name}, artista: {artist})")
    return result


def get_spotify_track_query(spotify_url: str) -> str | None:
    try:
        track_id = spotify_id_from_url(spotify_url)
        print(f"[DEBUG] Track ID extraído: {track_id}")
        track = sp.track(track_id)
        print(f"[DEBUG] Dados do Spotify recebidos: {track.get('name')} por {[a.get('name') for a in track.get('artists', [])]}")
        return spotify_track_to_query(track)
    except Exception as e:
        print(f"Erro ao acessar Spotify (track): {e}")
        return None


def get_spotify_playlist_queries(spotify_url: str, limit: int = MAX_SPOTIFY_ITEMS) -> list[str] | None:
    try:
        playlist_id = spotify_id_from_url(spotify_url)
        out: list[str] = []
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

        return [q for q in out if q and q != "unknown"]
    except Exception as e:
        print(f"Erro ao acessar Spotify (playlist): {e}")
        return None


def get_spotify_album_queries(spotify_url: str, limit: int = MAX_SPOTIFY_ITEMS) -> list[str] | None:
    try:
        album_id = spotify_id_from_url(spotify_url)
        out: list[str] = []
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

        return [q for q in out if q and q != "unknown"]
    except Exception as e:
        print(f"Erro ao acessar Spotify (album): {e}")
        return None


def make_watch_url_from_entry(entry: dict) -> str | None:
    if not entry:
        return None

    if entry.get("webpage_url"):
        return entry["webpage_url"]

    url = entry.get("url")
    if not url:
        return None

    # Às vezes vem só o id
    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", url):
        return f"https://www.youtube.com/watch?v={url}"

    # Às vezes vem uma URL já
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
            raise ValueError("Falha ao extrair informa??es do YouTube.")
        return data

    @classmethod
    async def from_data(cls, data: dict):
        stream_url = data.get("url")
        if not stream_url:
            raise ValueError("Não foi possível obter a URL de áudio.")
        return cls(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options), data=data)


async def ensure_voice(ctx) -> discord.VoiceClient | None:
    vc = ctx.voice_client
    if vc and vc.is_connected():
        return vc

    if ctx.author.voice and ctx.author.voice.channel:
        return await ctx.author.voice.channel.connect()

    await ctx.send("Entre em um canal de voz primeiro.")
    return None


def enqueue_search_strings(ctx, searches: list[str]) -> int:
    q = get_queue(ctx.guild.id)
    for s in searches:
        q.append({"_type": "search", "query": s})
    return len(searches)


def enqueue_watch_urls(ctx, urls: list[str]) -> int:
    q = get_queue(ctx.guild.id)
    for u in urls:
        q.append({"_type": "ytwatch", "url": u})
    return len(urls)


async def enqueue_youtube(ctx, yt_query: str) -> int:
    q = get_queue(ctx.guild.id)

    # Se for URL de playlist, enfileira watch URLs e resolve só quando tocar
    if is_youtube_url(yt_query) and looks_like_playlist_url(yt_query):
        data = await YTDLSource.extract_info(yt_query, loop=bot.loop)
        entries = data.get("entries") or []
        urls: list[str] = []

        for entry in entries:
            if not entry:
                continue
            watch = make_watch_url_from_entry(entry)
            if watch:
                urls.append(watch)

        return enqueue_watch_urls(ctx, urls)

    # Caso normal (vídeo único ou busca)
    if is_youtube_url(yt_query):
        return enqueue_watch_urls(ctx, [yt_query])

    data = await YTDLSource.extract_info(yt_query, loop=bot.loop)
    entries = data.get("entries") or []
    if not entries:
        return 0
    first = entries[0]
    watch = make_watch_url_from_entry(first)
    if not watch:
        return 0
    return enqueue_watch_urls(ctx, [watch])


async def resolve_queue_item_to_ytdlp_data(item: dict) -> dict:
    t = item.get("_type")

    if t == "search":
        query = (item.get("query") or "").strip()
        if not query:
            raise ValueError("Busca vazia.")
        data = await YTDLSource.extract_info(f"ytsearch1:{query}", loop=bot.loop)
        entries = data.get("entries") or []
        if not entries:
            raise ValueError(f"Nenhum resultado no YouTube para: {query}")
        watch = make_watch_url_from_entry(entries[0])
        if not watch:
            raise ValueError("Não consegui montar URL do resultado.")
        item = {"_type": "ytwatch", "url": watch}
        t = "ytwatch"

    if t == "ytwatch":
        url = (item.get("url") or "").strip()
        if not url:
            raise ValueError("URL vazia.")
        data = await YTDLSource.extract_info(url, loop=bot.loop)

        # Às vezes vem como entries (raro), pega o primeiro válido
        if "entries" in data:
            entries = data.get("entries") or []
            entries = [e for e in entries if e]
            if not entries:
                raise ValueError("Item indisponível.")
            data = entries[0]

        if not data.get("url"):
            raise ValueError("Sem stream (vídeo indisponível/bloqueado).")

        return data

    return item


async def start_playback_if_idle(ctx):
    lock = get_lock(ctx.guild.id)
    async with lock:
        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            return

        if vc.is_playing() or vc.is_paused():
            return

        q = get_queue(ctx.guild.id)
        while q:
            item = q.popleft()
            try:
                data = await resolve_queue_item_to_ytdlp_data(item)
                guild_now_playing[ctx.guild.id] = data
                player = await YTDLSource.from_data(data)
                break
            except Exception as e:
                await ctx.send(f"Pulando item (erro): {e}")
        else:
            guild_now_playing.pop(ctx.guild.id, None)
            return

        def _after(err):
            if err:
                print(f"Erro no player: {err}")
            bot.loop.create_task(start_playback_if_idle(ctx))

        vc.play(player, after=_after)

        if player.webpage_url:
            await ctx.send(f"Tocando agora: {player.title}\n{player.webpage_url}")
        else:
            await ctx.send(f"Tocando agora: {player.title}")


@bot.command(name="play")
async def play(ctx, *, query: str):
    vc = await ensure_voice(ctx)
    if not vc:
        return

    query = query.strip()

    async with ctx.typing():
        try:
            if is_spotify_track_url(query):
                print(f"[DEBUG] Detected Spotify TRACK url: {query}")
                qstr = get_spotify_track_query(query)
                print(f"[DEBUG] Query gerada do Spotify: {qstr}")
                if not qstr:
                    await ctx.send("Erro ao buscar a música no Spotify.")
                    return
                added = enqueue_search_strings(ctx, [qstr])
                print(f"[DEBUG] Adicionado à fila: {qstr}")

            elif is_spotify_playlist_url(query):
                print(f"[DEBUG] Detected Spotify PLAYLIST url: {query}")
                qs = get_spotify_playlist_queries(query, limit=MAX_SPOTIFY_ITEMS)
                print(f"[DEBUG] Queries geradas da playlist: {qs}")
                if not qs:
                    await ctx.send("Não consegui ler essa playlist do Spotify.")
                    return
                added = enqueue_search_strings(ctx, qs)
                print(f"[DEBUG] Adicionados à fila: {qs}")

            elif is_spotify_album_url(query):
                print(f"[DEBUG] Detected Spotify ALBUM url: {query}")
                qs = get_spotify_album_queries(query, limit=MAX_SPOTIFY_ITEMS)
                print(f"[DEBUG] Queries geradas do álbum: {qs}")
                if not qs:
                    await ctx.send("Não consegui ler esse álbum do Spotify.")
                    return
                added = enqueue_search_strings(ctx, qs)
                print(f"[DEBUG] Adicionados à fila: {qs}")

            else:
                if is_youtube_url(query):
                    yt_query = query
                else:
                    yt_query = query  # texto; resolve como search dentro do enqueue_youtube
                print(f"[DEBUG] Query para YouTube: {yt_query}")
                added = await enqueue_youtube(ctx, yt_query)

        except Exception as e:
            import traceback
            print(f"[DEBUG][ERRO] Falha ao adicionar na fila: {e}")
            traceback.print_exc()
            await ctx.send(f"Não consegui adicionar isso na fila: {e}")
            return

    if added == 0:
        await ctx.send("Não consegui adicionar nada na fila.")
        return

    if added == 1:
        await ctx.send("Adicionado 1 item na fila.")
    else:
        if added >= MAX_SPOTIFY_ITEMS and (is_spotify_playlist_url(query) or is_spotify_album_url(query)):
            await ctx.send(f"Adicionados {added} itens na fila (limitado a {MAX_SPOTIFY_ITEMS}).")
        else:
            await ctx.send(f"Adicionados {added} itens na fila.")

    await start_playback_if_idle(ctx)


@bot.command(name="queue")
async def queue_cmd(ctx):
    q = get_queue(ctx.guild.id)
    now = guild_now_playing.get(ctx.guild.id)

    lines = []
    if now:
        title = now.get("title") or "Sem título"
        url = now.get("webpage_url") or ""
        lines.append(f"Agora: {title}" + (f" - {url}" if url else ""))
    else:
        lines.append("Agora: nada tocando.")

    if not q:
        lines.append("Fila: vazia.")
        await ctx.send("\n".join(lines))
        return

    lines.append("Fila:")
    preview = list(q)[:10]
    for i, item in enumerate(preview, start=1):
        t = item.get("_type")
        if t == "search":
            lines.append(f"{i}. {item.get('query') or 'Sem título'}")
        elif t == "ytwatch":
            lines.append(f"{i}. {item.get('url') or 'Sem título'}")
        else:
            lines.append(f"{i}. Sem título")

    if len(q) > 10:
        lines.append(f"... e mais {len(q) - 10} item(ns).")

    await ctx.send("\n".join(lines))


@bot.command(name="skip")
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        await ctx.send("Eu não estou em canal de voz.")
        return

    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await ctx.send("Pulando para a próxima...")
    else:
        await ctx.send("Nada tocando agora.")


@bot.command(name="clear")
async def clear(ctx):
    q = get_queue(ctx.guild.id)
    q.clear()

    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()

    guild_now_playing.pop(ctx.guild.id, None)
    await ctx.send("Fila limpa.")


@bot.command(name="stop")
async def stop(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("Música parada!")
    else:
        await ctx.send("Nenhuma música tocando.")


@bot.command(name="pause")
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Pausado.")
    else:
        await ctx.send("Nada tocando agora.")


@bot.command(name="resume")
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Continuando...")
    else:
        await ctx.send("Nada pausado agora.")


@bot.command(name="leave")
async def leave(ctx):
    if ctx.voice_client and ctx.voice_client.is_connected():
        q = get_queue(ctx.guild.id)
        q.clear()
        guild_now_playing.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("Sai do canal de voz.")
    else:
        await ctx.send("Eu não estou em canal de voz.")


bot.run(TOKEN)
