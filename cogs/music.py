import asyncio
from collections import deque

import discord
from discord.ext import commands

from config import MAX_SPOTIFY_ITEMS
from utils.spotify import (
    is_spotify_track_url, is_spotify_playlist_url, is_spotify_album_url,
    get_spotify_track_query, get_spotify_playlist_queries, get_spotify_album_queries,
)
from utils.youtube import (
    is_youtube_url, looks_like_playlist_url, make_watch_url_from_entry, YTDLSource,
)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_queues: dict[int, deque] = {}
        self.guild_now_playing: dict[int, dict] = {}
        self.guild_locks: dict[int, asyncio.Lock] = {}

    def get_queue(self, guild_id: int) -> deque:
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = deque()
        return self.guild_queues[guild_id]

    def get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.guild_locks:
            self.guild_locks[guild_id] = asyncio.Lock()
        return self.guild_locks[guild_id]

    async def ensure_voice(self, ctx) -> discord.VoiceClient | None:
        vc = ctx.voice_client
        if vc and vc.is_connected():
            return vc

        if ctx.author.voice and ctx.author.voice.channel:
            return await ctx.author.voice.channel.connect()

        await ctx.send("Entre em um canal de voz primeiro.")
        return None

    def enqueue_search_strings(self, ctx, searches: list[tuple[str, str] | str]) -> int:
        q = self.get_queue(ctx.guild.id)
        for s in searches:
            if isinstance(s, tuple):
                query, display = s
                q.append({"_type": "search", "query": query, "display_title": display})
            else:
                q.append({"_type": "search", "query": s})
        return len(searches)

    def enqueue_watch_urls(self, ctx, urls: list[str]) -> int:
        q = self.get_queue(ctx.guild.id)
        for u in urls:
            q.append({"_type": "ytwatch", "url": u})
        return len(urls)

    async def enqueue_youtube(self, ctx, yt_query: str) -> int:
        if is_youtube_url(yt_query) and looks_like_playlist_url(yt_query):
            data = await YTDLSource.extract_info(yt_query, loop=self.bot.loop)
            entries = data.get("entries") or []
            urls: list[str] = []

            for entry in entries:
                if not entry:
                    continue
                watch = make_watch_url_from_entry(entry)
                if watch:
                    urls.append(watch)

            return self.enqueue_watch_urls(ctx, urls)

        if is_youtube_url(yt_query):
            return self.enqueue_watch_urls(ctx, [yt_query])

        data = await YTDLSource.extract_info(yt_query, loop=self.bot.loop)
        entries = data.get("entries") or []
        if not entries:
            return 0
        first = entries[0]
        watch = make_watch_url_from_entry(first)
        if not watch:
            return 0
        return self.enqueue_watch_urls(ctx, [watch])

    async def resolve_queue_item_to_ytdlp_data(self, item: dict) -> dict:
        t = item.get("_type")
        display_title = item.get("display_title")

        if t == "search":
            query = (item.get("query") or "").strip()
            if not query:
                raise ValueError("Busca vazia.")
            data = await YTDLSource.extract_info(f"ytsearch1:{query}", loop=self.bot.loop)
            entries = data.get("entries") or []
            if not entries:
                raise ValueError(f"Nenhum resultado no YouTube para: {query}")
            watch = make_watch_url_from_entry(entries[0])
            if not watch:
                raise ValueError("Não consegui montar URL do resultado.")
            item = {"_type": "ytwatch", "url": watch, "display_title": display_title}
            t = "ytwatch"

        if t == "ytwatch":
            url = (item.get("url") or "").strip()
            if not url:
                raise ValueError("URL vazia.")
            data = await YTDLSource.extract_info(url, loop=self.bot.loop)

            if "entries" in data:
                entries = data.get("entries") or []
                entries = [e for e in entries if e]
                if not entries:
                    raise ValueError("Item indisponível.")
                data = entries[0]

            if not data.get("url"):
                raise ValueError("Sem stream (vídeo indisponível/bloqueado).")

            if display_title:
                data["display_title"] = display_title

            return data

        return item

    async def start_playback_if_idle(self, ctx):
        lock = self.get_lock(ctx.guild.id)
        async with lock:
            vc = ctx.voice_client
            if not vc or not vc.is_connected():
                return

            if vc.is_playing() or vc.is_paused():
                return

            q = self.get_queue(ctx.guild.id)
            while q:
                item = q.popleft()
                try:
                    data = await self.resolve_queue_item_to_ytdlp_data(item)
                    self.guild_now_playing[ctx.guild.id] = data
                    player = await YTDLSource.from_data(data)
                    break
                except Exception as e:
                    await ctx.send(f"Pulando item (erro): {e}")
            else:
                self.guild_now_playing.pop(ctx.guild.id, None)
                return

            def _after(err):
                if err:
                    print(f"Erro no player: {err}")
                self.bot.loop.create_task(self.start_playback_if_idle(ctx))

            vc.play(player, after=_after)

            display = data.get("display_title") or player.title
            if player.webpage_url:
                await ctx.send(f"Tocando agora: [{display}](<{player.webpage_url}>)")
            else:
                await ctx.send(f"Tocando agora: {display}")

    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        vc = await self.ensure_voice(ctx)
        if not vc:
            return

        query = query.strip()

        async with ctx.typing():
            try:
                if is_spotify_track_url(query):
                    print(f"[DEBUG] Detected Spotify TRACK url: {query}")
                    result = get_spotify_track_query(query)
                    print(f"[DEBUG] Query gerada do Spotify: {result}")
                    if not result:
                        await ctx.send("Erro ao buscar a música no Spotify.")
                        return
                    added = self.enqueue_search_strings(ctx, [result])
                    print(f"[DEBUG] Adicionado à fila: {result}")

                elif is_spotify_playlist_url(query):
                    print(f"[DEBUG] Detected Spotify PLAYLIST url: {query}")
                    qs = get_spotify_playlist_queries(query, limit=MAX_SPOTIFY_ITEMS)
                    print(f"[DEBUG] Queries geradas da playlist: {qs}")
                    if not qs:
                        await ctx.send("Não consegui ler essa playlist do Spotify.")
                        return
                    added = self.enqueue_search_strings(ctx, qs)
                    print(f"[DEBUG] Adicionados à fila: {qs}")

                elif is_spotify_album_url(query):
                    print(f"[DEBUG] Detected Spotify ALBUM url: {query}")
                    qs = get_spotify_album_queries(query, limit=MAX_SPOTIFY_ITEMS)
                    print(f"[DEBUG] Queries geradas do álbum: {qs}")
                    if not qs:
                        await ctx.send("Não consegui ler esse álbum do Spotify.")
                        return
                    added = self.enqueue_search_strings(ctx, qs)
                    print(f"[DEBUG] Adicionados à fila: {qs}")

                else:
                    yt_query = query
                    print(f"[DEBUG] Query para YouTube: {yt_query}")
                    added = await self.enqueue_youtube(ctx, yt_query)

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

        await self.start_playback_if_idle(ctx)

    @commands.command(name="queue")
    async def queue_cmd(self, ctx):
        q = self.get_queue(ctx.guild.id)
        now = self.guild_now_playing.get(ctx.guild.id)

        lines = []
        if now:
            title = now.get("display_title") or now.get("title") or "Sem título"
            lines.append(f"Agora: {title}")
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
                label = item.get("display_title") or item.get("query") or "Sem título"
                lines.append(f"{i}. {label}")
            elif t == "ytwatch":
                lines.append(f"{i}. {item.get('url') or 'Sem título'}")
            else:
                lines.append(f"{i}. Sem título")

        if len(q) > 10:
            lines.append(f"... e mais {len(q) - 10} item(ns).")

        await ctx.send("\n".join(lines))

    @commands.command(name="skip")
    async def skip(self, ctx):
        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            await ctx.send("Eu não estou em canal de voz.")
            return

        if vc.is_playing() or vc.is_paused():
            vc.stop()
            await ctx.send("Pulando para a próxima...")
        else:
            await ctx.send("Nada tocando agora.")

    @commands.command(name="clear")
    async def clear(self, ctx):
        q = self.get_queue(ctx.guild.id)
        q.clear()

        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

        self.guild_now_playing.pop(ctx.guild.id, None)
        await ctx.send("Fila limpa.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send("Música parada!")
        else:
            await ctx.send("Nenhuma música tocando.")

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

    @commands.command(name="leave")
    async def leave(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            q = self.get_queue(ctx.guild.id)
            q.clear()
            self.guild_now_playing.pop(ctx.guild.id, None)
            await ctx.voice_client.disconnect()
            await ctx.send("Sai do canal de voz.")
        else:
            await ctx.send("Eu não estou em canal de voz.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
