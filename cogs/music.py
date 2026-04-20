import asyncio
import random
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from config import FFMPEG_OPTIONS, MAX_PLAYLIST_ITEMS
from utils.youtube import ytdl, is_youtube_url, is_playlist_url
from utils.spotify import (
    is_spotify_track_url, is_spotify_playlist_url, is_spotify_album_url,
    get_spotify_track_query, get_spotify_playlist_queries, get_spotify_album_queries,
)

_ytdl_lock = asyncio.Lock()
_ytdl_next_call = 0.0
_REQUEST_GAP = 2.0


def _watch_url(entry: dict) -> str | None:
    if not entry:
        return None
    if entry.get("webpage_url"):
        return entry["webpage_url"]
    url = entry.get("url", "")
    return url if url.startswith("http") else None


async def _extract_info(query: str) -> dict:
    global _ytdl_next_call
    loop = asyncio.get_running_loop()

    async with _ytdl_lock:
        wait = _ytdl_next_call - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

        data, last_err = None, None
        for attempt in range(3):
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))

        _ytdl_next_call = time.monotonic() + _REQUEST_GAP + random.uniform(0, 1.0)

    if data is None:
        raise last_err or ValueError("Falha ao extrair informações.")
    return data


async def _resolve(item: dict) -> dict:
    query = item["query"]
    data = await _extract_info(query if query.startswith("http") else f"ytsearch1:{query}")

    if "entries" in data:
        entries = [e for e in (data.get("entries") or []) if e]
        if not entries:
            raise ValueError("Sem resultados.")
        data = entries[0]

    if not data.get("url"):
        raise ValueError("Sem stream disponível (bloqueado ou indisponível).")

    if item.get("display"):
        data["display_title"] = item["display"]
    return data


IDLE_TIMEOUT = 300
QUEUE_DISPLAY_LIMIT = 10


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: defaultdict[int, deque] = defaultdict(deque)
        self.now_playing: dict[int, dict] = {}
        self.locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._idle_tasks: dict[int, asyncio.Task] = {}

    def _cancel_idle(self, guild_id: int):
        task = self._idle_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    def _start_idle(self, guild_id: int):
        self._cancel_idle(guild_id)
        self._idle_tasks[guild_id] = asyncio.create_task(self._idle_disconnect(guild_id))

    async def _idle_disconnect(self, guild_id: int):
        await asyncio.sleep(IDLE_TIMEOUT)
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.is_connected():
            if not guild.voice_client.is_playing() and not guild.voice_client.is_paused():
                self.queues[guild_id].clear()
                self.now_playing.pop(guild_id, None)
                await guild.voice_client.disconnect()

    def _enqueue(self, guild_id: int, query: str, display: str | None = None):
        self.queues[guild_id].append({"query": query, "display": display})

    async def _ensure_voice(self, ctx) -> discord.VoiceClient | None:
        if ctx.voice_client and ctx.voice_client.is_connected():
            return ctx.voice_client
        if ctx.author.voice and ctx.author.voice.channel:
            return await ctx.author.voice.channel.connect()
        await ctx.send("Entre em um canal de voz primeiro.")
        return None

    async def _add_to_queue(self, ctx, query: str) -> int:
        if is_spotify_track_url(query):
            result = get_spotify_track_query(query)
            if not result:
                await ctx.send("Erro ao buscar a música no Spotify.")
                return 0
            self._enqueue(ctx.guild.id, *result)
            return 1

        if is_spotify_playlist_url(query):
            tracks = get_spotify_playlist_queries(query)
            if not tracks:
                await ctx.send("Não consegui ler essa playlist do Spotify.")
                return 0
            for q, d in tracks:
                self._enqueue(ctx.guild.id, q, d)
            return len(tracks)

        if is_spotify_album_url(query):
            tracks = get_spotify_album_queries(query)
            if not tracks:
                await ctx.send("Não consegui ler esse álbum do Spotify.")
                return 0
            for q, d in tracks:
                self._enqueue(ctx.guild.id, q, d)
            return len(tracks)

        if is_youtube_url(query) and is_playlist_url(query):
            data = await _extract_info(query)
            entries = [e for e in (data.get("entries") or []) if e]
            urls = [u for e in entries[:MAX_PLAYLIST_ITEMS] if (u := _watch_url(e))]
            for url in urls:
                self._enqueue(ctx.guild.id, url)
            return len(urls)

        self._enqueue(ctx.guild.id, query)
        return 1

    async def _play_next(self, ctx):
        async with self.locks[ctx.guild.id]:
            vc = ctx.voice_client
            if not vc or not vc.is_connected() or vc.is_playing() or vc.is_paused():
                return

            q = self.queues[ctx.guild.id]
            while q:
                item = q.popleft()
                try:
                    data = await _resolve(item)
                    self.now_playing[ctx.guild.id] = data
                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(data["url"], **FFMPEG_OPTIONS)
                    )
                    break
                except Exception as e:
                    await ctx.send(f"Pulando item (erro): {e}")
            else:
                self.now_playing.pop(ctx.guild.id, None)
                self._start_idle(ctx.guild.id)
                return

            self._cancel_idle(ctx.guild.id)

            def after(err):
                if err:
                    print(f"Erro no player: {err}")
                asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop)

            vc.play(source, after=after)
            title = data.get("display_title") or data.get("title") or "Sem título"
            url = data.get("webpage_url")
            msg = f"Tocando agora: [{title}](<{url}>)" if url else f"Tocando agora: {title}"
            await ctx.send(msg)

    @commands.command(name="join")
    async def join(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("Entre em um canal de voz primeiro.")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        self._start_idle(ctx.guild.id)
        await ctx.send(f"Entrei em **{channel.name}**.")

    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        vc = await self._ensure_voice(ctx)
        if not vc:
            return

        async with ctx.typing():
            try:
                added = await self._add_to_queue(ctx, query.strip())
            except Exception as e:
                await ctx.send(f"Não consegui adicionar isso na fila: {e}")
                return

        if added == 0:
            return
        elif added == 1:
            await ctx.send("Adicionado 1 item na fila.")
        elif added >= MAX_PLAYLIST_ITEMS:
            await ctx.send(f"Adicionados {added} itens na fila (limitado a {MAX_PLAYLIST_ITEMS}).")
        else:
            await ctx.send(f"Adicionados {added} itens na fila.")

        await self._play_next(ctx)

    @commands.command(name="queue")
    async def queue_cmd(self, ctx):
        now = self.now_playing.get(ctx.guild.id)
        q = self.queues[ctx.guild.id]

        current = now.get("display_title") or now.get("title") or "Sem título" if now else "nada tocando"
        lines = [f"Agora: {current}"]

        if not q:
            lines.append("Fila: vazia.")
            await ctx.send("\n".join(lines))
            return

        lines.append("Fila:")
        for i, item in enumerate(list(q)[:QUEUE_DISPLAY_LIMIT], 1):
            lines.append(f"{i}. {item.get('display') or item.get('query') or 'Sem título'}")
        if len(q) > QUEUE_DISPLAY_LIMIT:
            lines.append(f"... e mais {len(q) - QUEUE_DISPLAY_LIMIT} item(ns).")
        await ctx.send("\n".join(lines))

    @commands.command(name="skip")
    async def skip(self, ctx):
        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            await ctx.send("Não estou em canal de voz.")
            return
        if vc.is_playing() or vc.is_paused():
            vc.stop()
            await ctx.send("Pulando")
        else:
            await ctx.send("Nada tocando agora.")

    @commands.command(name="pause")
    async def pause(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("Pausado.")
        else:
            await ctx.send("Nada tocando agora.")

    @commands.command(name="resume")
    async def resume(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("Continuando...")
        else:
            await ctx.send("Nada pausado agora.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send("Música parada!")
        else:
            await ctx.send("Nenhuma música tocando.")

    @commands.command(name="clear")
    async def clear(self, ctx):
        self.queues[ctx.guild.id].clear()
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        self.now_playing.pop(ctx.guild.id, None)
        await ctx.send("Fila limpa.")

    @commands.command(name="leave")
    async def leave(self, ctx):
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.send("Não estou em canal de voz.")
            return
        self._cancel_idle(ctx.guild.id)
        self.queues[ctx.guild.id].clear()
        self.now_playing.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
        await ctx.send("Saindo do canal de voz.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
