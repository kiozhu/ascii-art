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
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot token for bot control |
| `TIKTOK_USERNAME` | Optional | TikTok username to monitor (no password needed) |

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
| **DISPLAY** | Manual text, image upload, video upload, clear display |
| **SETTINGS** | Font (7 styles), FG/BG color, gradient, matrix rain, screenshot mode |
| **TIKTOK LIVE** | Connect by username, residential proxy support, room ID input |
| **GIFT** | Test animations, blink/duration/speed/sound settings |
| **🤖 AUTO REPLY** | Enable/disable, queue monitor, riddle list, test comment/riddle |

### TikTok Live Integration

- **Gift display** — 30+ animated ASCII art gifts (rose, crown, rocket, dragon, etc.)
- **Chat comments** — displayed as badges on overlay
- **Username display** — ASCII art username with glitch effect
- **Robot eyes animation** — 4-scene sequence per gift
- **TTS voice** — gTTS reads username + reply aloud

### AI Auto-Reply (🤖 Auto Reply Tab)

**Riddle system** — Background tebak-tebakan cycle:
- ASK → 5s → ANSWER → 5s → CTA → 5s → next riddle
- 40 riddles (absurd, logika, budaya, tech)
- Skipped automatically when comment queue has items

**Comment reply** — Top priority over riddles:
- Strict serial: **1 reply every 7 seconds**
- No batching, no overlap ever
- Reply lock held during full display duration
- 36 funny/sopan replies (≤5 words each)

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
│   ├── image.py            # Image → ASCII
│   ├── video.py            # Video frame → ASCII
│   └── block_art.py        # Block art
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
- **eventlet** / **threading** — async background processing