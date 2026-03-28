# Discord Music Bot

Um bot de música para Discord que toca músicas do YouTube e permite buscar faixas, playlists e álbuns do Spotify (buscando no YouTube automaticamente).

## Funcionalidades
- Comando `.play <link ou texto>`: Toca músicas do YouTube ou busca por nome/artista
- Aceita links do Spotify (track, playlist, álbum) e converte para busca no YouTube
- Comandos de fila: `.queue`, `.skip`, `.clear`, `.pause`, `.resume`, `.stop`, `.leave`
- Suporte a múltiplos servidores

## Como funciona
- Ao receber um link do Spotify, o bot consulta a API do Spotify para obter nome e artista
- Busca a música correspondente no YouTube e toca no canal de voz
- Utiliza as bibliotecas `discord.py`, `yt-dlp`, `spotipy`

## Pré-requisitos
- Python 3.9+
- Conta no Discord e Spotify (pode ser gratuita)
- Token do bot Discord
- Credenciais do Spotify Developer (Client ID e Secret)

## Instalação
1. Clone o repositório
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Crie um arquivo `.env` com:
   ```env
   DISCORD_TOKEN=seu_token_aqui
   SPOTIPY_CLIENT_ID=seu_client_id_aqui
   SPOTIPY_CLIENT_SECRET=seu_client_secret_aqui
   ```
4. Execute o bot:
   ```bash
   python main.py
   ```

## Comandos
- `.play <url ou texto>` — Toca música do YouTube ou busca por nome/artista
- `.play <link do Spotify>` — Busca a faixa/playlist/álbum no YouTube e toca
- `.queue` — Mostra a fila
- `.skip` — Pula para a próxima
- `.clear` — Limpa a fila
- `.pause` — Pausa a música
- `.resume` — Continua a música
- `.stop` — Para a música
- `.leave` — Sai do canal de voz

## Estrutura do Projeto
```
discord-bot/
├── main.py              # Entrada: cria o bot e carrega os cogs
├── config.py            # Configurações (ytdl, spotify, constantes)
├── utils/
│   ├── spotify.py       # Helpers do Spotify (track, playlist, álbum)
│   └── youtube.py       # YTDLSource e helpers do YouTube
├── cogs/
│   └── music.py         # Comandos de música (Cog do discord.py)
├── requirements.txt
└── .env
```

## Observações
- O bot **não toca áudio diretamente do Spotify** (por restrições da API), apenas busca no YouTube
- Para melhor funcionamento, mantenha o `yt-dlp` sempre atualizado
- O bot funciona em múltiplos servidores simultaneamente

## Licença
MIT