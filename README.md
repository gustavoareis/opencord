# Discord Bot

Bot de Discord com módulos de música e IA.

## Funcionalidades

### Geral

| Comando | Descrição |
|---|---|
| `.salve` | Cumprimento do bot |

### Música
Reproduz áudio em canais de voz com suporte a YouTube e Spotify. O bot desconecta automaticamente após 5 minutos sem tocar nada.

| Comando | Descrição |
|---|---|
| `.join` | Entra no canal de voz do usuário |
| `.play <query>` | Toca uma música ou adiciona à fila (YouTube, Spotify ou busca por texto) |
| `.queue` | Exibe a fila atual e o que está tocando |
| `.skip` | Pula para a próxima música |
| `.pause` | Pausa a reprodução |
| `.resume` | Retoma a reprodução |
| `.stop` | Para a música atual |
| `.clear` | Limpa a fila e para a reprodução |
| `.leave` | Desconecta do canal de voz |

**Formatos aceitos pelo `.play`:**
- Busca por texto: `.play never gonna give you up`
- URL do YouTube: `.play https://youtube.com/watch?v=...`
- Playlist do YouTube: `.play https://youtube.com/playlist?list=...`
- Música do Spotify: `.play https://open.spotify.com/track/...`
- Playlist do Spotify: `.play https://open.spotify.com/playlist/...`
- Álbum do Spotify: `.play https://open.spotify.com/album/...`

### IA
| Comando | Descrição |
|---|---|
| `.chat <pergunta>` | Envia uma pergunta para o modelo Llama 3.3 70B via Groq |

## Instalação

**Pré-requisitos:** Python 3.10+, FFmpeg instalado e no PATH.

```bash
# Clone o repositório
git clone https://github.com/gustavoareis/discord-bot.git
cd discord-bot

# Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

## Configuração

Copie o arquivo de exemplo e preencha as variáveis:

```bash
cp .exemple.env .env
```

```env
DISCORD_TOKEN=        # Token do bot no Discord Developer Portal
SPOTIPY_CLIENT_ID=    # Client ID do app no Spotify for Developers
SPOTIPY_CLIENT_SECRET=# Client Secret do app no Spotify for Developers
GROQ_API_KEY=         # Chave de API da Groq
```

## Executar

```bash
python main.py
```

## Tecnologias

- [discord.py](https://discordpy.readthedocs.io/) — framework do bot
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download e stream de áudio do YouTube
- [spotipy](https://spotipy.readthedocs.io/) — integração com a API do Spotify
- [Groq](https://groq.com/) — inferência de LLM (Llama 3.3 70B)
- [PyNaCl](https://pynacl.readthedocs.io/) — suporte a voz no Discord

## Licença

[MIT](LICENSE)
