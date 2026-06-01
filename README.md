# ASCII Art Overlay System

Real-time ASCII art overlay for live streaming (OBS). Flask + SocketIO powered, TikTok integration, animated gift display, matrix rain background, screenshot & recording, full Control Panel.

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone git@github.com:kiozhu/ascii-art.git
cd ascii-art
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TIKTOK_USERNAME=your_tiktok_username
TIKTOK_PASSWORD=your_tiktok_password
```

### 4. Run

```bash
python app.py
```

Open your browser:
- **Overlay:** `http://localhost:5050` (use in OBS)
- **Control Panel:** `http://localhost:5050/control`
- **Logs:** `http://localhost:5050/logs`

---

## 🖥️ OBS Setup

1. In OBS, add a **Browser Source**
2. URL: `http://localhost:5050` (or `http://YOUR_IP:5050` for remote)
3. Width: `1920`, Height: `1080`
4. CSS custom style:
   ```css
   body { overflow: hidden; margin: 0; padding: 0; background: #000; }
   ```
5. Refresh on launch: **No**

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for bot control |
| `TIKTOK_USERNAME` | TikTok username for live chat |
| `TIKTOK_PASSWORD` | TikTok password |

### Control Panel Options

| Setting | Options |
|---------|---------|
| **Font** | ansi_shadow, blocky, starwars, banner3, banner4, banner, rounded |
| **FG Color** | Hex color (e.g. `#ffd700`) |
| **BG Color** | Hex background color |
| **Gradient** | Top/Mid/Bot colors for gradient effect |
| **Matrix** | Toggle on/off, speed, color |
| **Screenshot** | Flash effect, aspect ratio (square/vertical/horizontal/none) |
| **Recording** | Duration 3–30s, auto or manual trigger |
| **Gift Animation** | Blink duration, display duration, typing speed, sound on/off |

---

## 🎁 Gift Animation Flow

1. **Robot Eyes** — 4-scene animation (neutral → lookLeft → lookRight → close)
2. **Thanks Text** — "terima kasih @username" with glitch effect
3. **Username ASCII Art** — username rendered in ansi_shadow font, pulsing glow

---

## 🛠️ Tech Stack

- **Flask** + **SocketIO** — real-time web server
- **pyfiglet** — ASCII text rendering
- **html2canvas** — screenshot capture
- **TikTok Pcap** — live chat integration
- **Telegram Bot API** — bot control interface

---

## 📁 Project Structure

```
ascii-art/
├── app.py                  # Main Flask app + WebSocket handlers
├── app_gift_section.py     # Gift animation server-side logic
├── converters/
│   ├── text.py            # Text to ASCII conversion
│   ├── image.py            # Image to ASCII conversion
│   ├── video.py            # Video frame to ASCII
│   └── block_art.py       # Block art converter
├── templates/
│   ├── overlay.html        # Main overlay (OBS view)
│   ├── control.html       # Streamer control panel
│   └── logs.html          # Event logs viewer
├── telegram_bot/
│   └── bot.py             # Telegram bot integration
├── tiktok/
│   └── connector.py       # TikTok live chat connector
├── requirements.txt
├── .env.example
└── README.md
```

---

**Streaming setup guide:** [OBS Browser Source](https://obsproject.com/kb/browser-source)