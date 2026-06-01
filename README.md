# ASCII Art Overlay System

Real-time ASCII art overlay for live streaming (OBS). Flask + SocketIO powered, TikTok integration, animated gift display, matrix rain background, screenshot & recording, full Control Panel.

## Features

- **OBS Overlay** — obs-studio compatible via browser source
- **TikTok Live Integration** — gifts & comments real-time display
- **Animated Gift Scenes** — robot eyes sequence → username ASCII art
- **Matrix Rain Background** — toggleable animated background
- **Screenshot & Recording** — one-click capture (manual or auto on event)
- **Control Panel** — font, color, gradient, aspect ratio, duration
- **Multiple Aspect Ratios** — square, vertical (9:16), horizontal (16:9)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit environment config
cp .env.example .env
# Fill in your Telegram bot token and TikTok credentials in .env

# Run server
python app.py
```

Open `http://localhost:5050` — overlay, `http://localhost:5050/control` — control panel.

## OBS Setup

1. Add **Browser Source** in OBS
2. URL: `http://localhost:5050` (or your public IP)
3. Width: `1920`, Height: `1080`
4. CSS custom: `body { overflow: hidden; }`
5. Refresh on launch: `No`

## Configuration

| Setting | Description |
|---------|-------------|
| Font | ansi_shadow, blocky, starwars, banner3, banner4, banner, rounded |
| Colors | fg color, bg color, gradient top/mid/bot |
| Matrix | toggle on/off + speed + color |
| Screenshot | flash effect, aspect ratio |
| Recording | duration 3–30s, auto/manual |
| Gift | blink duration, display duration, typing speed, sound |

## Tech Stack

Flask · SocketIO · pyfiglet · html2canvas · TikTok Pcap · Telegram Bot API

---

**Streaming setup guide:** [OBS Browser Source](https://obsproject.com/kb/browser-source)