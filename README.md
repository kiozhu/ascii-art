# ASCII Art Overlay System

Real-time ASCII art overlay for live streaming (OBS). Flask + Socket.IO powered, TikTok Live chat integration, AI auto-reply with riddles, animated gift display, TTS voice, matrix rain, screenshot & recording, full Control Panel.

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone git@github.com:kiozhu/ascii-art.git
cd ascii-art
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — only TELEGRAM_BOT_TOKEN is required; TikTok is optional
```

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

### 3. Run

```bash
python app.py
```

Open your browser:
- **Overlay:** `http://localhost:5050` (use in OBS)
- **Control Panel:** `http://localhost:5050/control`

---

## 🖥️ OBS Setup

1. Add a **Browser Source** in OBS
2. URL: `http://localhost:5050` (or `http://YOUR_IP:5050` for remote)
3. Width: `1920`, Height: `1080`
4. CSS:
   ```css
   body { overflow: hidden; margin: 0; padding: 0; background: #000; }
   ```
5. Refresh on launch: **No**

---

## ⚙️ Configuration

Copy `.env.example` to `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot token (get from @BotFather) |
| `TELEGRAM_ADMIN_CHAT_ID` | Optional | Your Telegram chat ID (get from @userinfobot) |
| `TELEGRAM_ENABLED` | Optional | Set `true` to enable bot, or configure via Control Panel |
| `TIKTOK_USERNAME` | Optional | TikTok username to monitor (no password needed) |
| `MINIMAX_API_KEY` | Optional | MiniMax API key for LLM auto-reply + dynamic riddles |
| `MINIMAX_BASE_URL` | Optional | MiniMax API base URL (default: `https://api.minimax.io/anthropic`) |
| `MINIMAX_MODEL` | Optional | Model name (`MiniMax-M3` or `MiniMax-M2.7`, default: `MiniMax-M2.7`) |
| `MINIMAX_ENABLED` | Optional | Set `true` to enable LLM, or configure via Control Panel |

> **Telegram bot config** — Set token + chat ID directly in **Control Panel → Settings → Telegram Bot** section. No need to edit .env manually.

> **MiniMax LLM config** — Set API key + model + enable directly in **Control Panel → Settings → MiniMax LLM** section. No need to edit .env manually.

> **No TikTok credentials needed** — TikTokLive uses anonymous WebSocket connection via username only.

### TikTok Residential Proxy (VPS Only)

If running on a VPS, TikTok may block the connection due to data-center IP. Add a residential proxy:

1. Get a residential proxy (Bright Data, Oxylabs, SmartProxy)
2. In **Control Panel → TikTok Live**, enter your proxy URL:
   ```
   http://user:pass@host:port
   ```
3. Click **CONNECT**

---

## 🎮 Features

### Control Panel (`/control`)

| Tab | Features |
|-----|----------|
| **DISPLAY** | Manual text, image upload, clear display |
| **SETTINGS** | Font (7 styles), FG/BG color, gradient, matrix rain, screenshot mode, **Telegram Bot config**, **MiniMax LLM config** |
| **TIKTOK LIVE** | Connect by username, residential proxy support, room ID input |
| **GIFT** | Test animations, blink/duration/speed/sound settings |
| **🤖 AUTO REPLY** | Enable/disable, queue monitor, riddle list, test comment/riddle |

### TikTok Live Integration

- **Gift display** — 30+ animated ASCII art gifts (rose, crown, rocket, dragon, etc.)
- **Chat comments** — displayed as badges on overlay
- **Username display** — ASCII art username with glitch effect
- **Robot eyes animation** — 4-scene sequence per gift
- **TTS voice** — gTTS reads username + reply aloud

### Telegram Bot (`/control → Settings → Telegram Bot`)

Configure bot token + admin chat ID directly from the control panel — no .env editing needed.

Commands (prefix `ascii`, e.g. `/ascii display hello`):

| Command | Description |
|---------|-------------|
| `/ascii display <text>` | Display text on overlay |
| `/ascii big <text>` | Big ASCII art text |
| `/ascii block <text>` | Pixel block text |
| `/ascii half <text>` | Half-block shading |
| `/ascii clear` | Clear overlay |
| `/ascii tiktok <user>` | Connect to TikTok room |
| `/ascii status` | Server status |
| Direct text | Just type to display |

Reply to a photo with `/ascii image` to send it to overlay.

### AI Auto-Reply (🤖 Auto Reply Tab)

**MiniMax LLM integration** — when enabled, uses MiniMax M2.7 or M3 for natural dynamic responses:
- **Comment reply** — generates natural, context-aware replies (max 5 words)
- **Riddle generation** — creates new tebak-tebakan dynamically (JSON: `{"q": "...", "a": "..."}`)
- Falls back to static pool if LLM unavailable

**Fallback indicator** — overlay visually distinguishes LLM vs static:
- `[AI]` tag = LLM-generated riddles (cyan question / gold answer)
- `[static]` tag = static pool fallback (red question / red answer / red glow)
- TTS appends "[static]" when reading fallback answers
- Logs show `[RIDDLE ASK: [static]]` vs `[RIDDLE ASK: ...]` to track fallback events

**Riddle system** — background tebak-tebakan cycle:
- ASK → 5s → ANSWER → 5s → CTA → 5s → next riddle
- 40 static riddles (absurd, logika, budaya, tech) — replaced by LLM when enabled
- Skipped automatically when comment queue has items

**No emoji policy** — all output is clean text:
- LLM replies stripped of emoji via `_remove_emoji()` regex
- Static pool (FUNNY_REPLIES) pre-cleaned — no emoji
- Overlay labels stripped of emoji ("AUTO REPLY" not "🤖 AUTO REPLY")
- TTS reads clean text only

**Comment reply** — top priority over riddles:
- Komentar diproses satu-per-satu (tidak batching)
- 7 detik tampil, tidak overlap dengan riddle/CTA

**Display collision prevention** — strict priority system:
| Source | Priority | Notes |
|--------|----------|-------|
| Auto Reply | 4 (highest) | Komentar masuk — preempt semua |
| Manual Display | 3 | User ketik manual — preempt riddle/CTA |
| Riddle ASK/ANSWER | 2 | Preempt CTA saja |
| CTA | 1 (lowest) | Di-preempt oleh semua di atas |

**Race condition prevention** — per-source sequence numbers:
- Setiap emit Socket.IO disertai `seq` counter per source
- Browser track `window._lastSeq[source]` — event dengan seq lebih rendah di-drop
- Bergaransi urutan satu-per-satu bahkan dengan HTTP long-polling transport
- Strict serial: **1 reply every 7 seconds**
- No batching, no overlap ever
- Reply lock held during full display duration
- 36 funny/sopan replies (≤5 words each) — replaced by LLM when enabled

**TTS** — gTTS reads all riddle phases + replies aloud

---

## 📁 Project Structure

```
ascii-art/
├── app.py                  # Flask + Socket.IO + TTS + auto-reply loop
├── app_gift_section.py     # Gift animation server-side
├── tiktok/
│   └── connector.py        # TikTokLive WebSocket connector (web_proxy/ws_proxy)
├── converters/
│   ├── text.py             # Text → ASCII
│   ├── image.py            # Image → ASCII (Pillow)
│   └── blocktext.py        # Block text
├── templates/
│   ├── overlay.html         # OBS overlay (canvas + Socket.IO client)
│   ├── control.html        # Streamer control panel (5 tabs)
│   └── logs.html           # Event logs
├── telegram_bot/
│   └── bot.py              # Telegram bot commands
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🛠️ Tech Stack

- **Flask** + **Socket.IO** — real-time web server & WebSocket
- **pyfiglet** — ASCII text rendering
- **TikTokLive** — TikTok live chat WebSocket (v6.6.5)
- **gTTS** — Google text-to-speech (server-side, suara cewek)
- **requests** — MiniMax LLM API calls (HTTP)
- **eventlet** / **threading** — async background processing