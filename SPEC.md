# ASCII Overlay — Live Streaming System

## Concept & Vision

Sistem overlay interaktif untuk live streaming yang mengubah teks, gambar, GIF, dan video menjadi tampilan ASCII art real-time. Mengadopsi gaya terminal futuristik / Matrix — hijau neon di atas hitam, kesan hacker futuristik. Ditampilkan via OBS Browser Source, membuat live coding / AI / teknologi terlihat jauh lebih menarik.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Flask Server (port 5050)                   │
│                                                              │
│  ┌──────────────┐  WebSocket  ┌─────────────────┐          │
│  │ Control Panel │◄──────────►│  Overlay View    │          │
│  │ (streamer)    │             │ (OBS Browser Src)│          │
│  └──────────────┘             └─────────────────┘          │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐  ┌────────────────────────┐  ┌──────────┐  │
│  │ Logs Dashboard│  │ TikTok WS Connector   │  │  gTTS    │  │
│  └──────────────┘  └────────────────────────┘  │  (TTS)    │  │
│                                                └──────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Auto-Reply Loop (background thread)                     │  │
│  │  - Riddle cycle: ASK→ANS→CTA→ASK                         │  │
│  │  - Comment queue: strict serial 1 reply / 7s              │  │
│  │  - Comment priority over riddles                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Port:** 5050 (Flask + WebSocket)

**3 Interfaces:**
- `overlay.html` — Tampilan live (OBS Browser Source)
- `control.html` — Panel kontrol streamer (5 tabs)
- `logs.html` — Monitoring & log

---

## Visual Identity

- **Dominan:** Hitam `#000` + hijau neon `#00ff41`
- **Font:** Monospace (Courier New / Fira Code)
- **Style:** Terminal / Matrix / Cyberpunk
- **Effects:** Matrix rain background, glow effects, flicker

---

## TikTok Integration

**Method:** TikTokLive (WebSocket) — anonymous connection via username only

- Connect ke live stream via room ID (username TikTok)
- Listen untuk `comment` dan `gift` events
- Relay ke overlay via Socket.IO

**Proxy support:** Residential proxy (`web_proxy` / `ws_proxy`) untuk koneksi dari VPS (IP data center diblokir TikTok)

**Status flow:**
```
Server Starting → Connecting → Connected → Live
                                      ↘ Disconnected → Reconnecting...
```

---

## AI Auto-Reply System

### Riddle Cycle (background)

```
ASK (teka-teki) → 5s → ANSWER (jawaban) → 5s → CTA (ajak comentar) → 5s → next ASK
```

- Pool: 40 tebak-tebakan (absurd, logika, budaya, tech)
- Riddle DILEWATKAN jika ada komentar di antrian
- Auto-clear: 8s (riddle ask), 5s (CTA)
- TTS gTTS dibaca di setiap phase

### Comment Reply (priority tinggi)

- Strict serial: **1 reply every 7 seconds**
- No batching, no overlap
- `reply_locked = True` selama 7s (ditahan pakai `time.sleep`)
- Riddle timer di-reset ke `reply_display_sec` (7s) setelah reply selesai
- 36 funny/sopan replies (≤5 words each, semua sopan)

### Display Colors

| Event | Color | Label |
|-------|-------|-------|
| Riddle ASK | Cyan `#00ffff` | 💬 TEBAK |
| Riddle ANSWER | Gold `#ffd700` | 💬 JAWABAN |
| CTA | Pink `#ff1493` | 💬 HEY SOB |
| Auto Reply | Neon green `#39ff14` | Auto Reply |
| Comment Badge | White `#ffffff` | @username |
| Gift | Rainbow gradient | 🎁 |

---

## Gift Animation

1. **Robot Eyes** — 4-scene animation (neutral → lookLeft → lookRight → close)
2. **Thanks Text** — "terima kasih @username" with glitch effect
3. **Username ASCII Art** — username rendered in ansi_shadow font, pulsing glow
4. **Gift ASCII Art** — 30+ types (rose, crown, rocket, dragon, phone, etc.)

---

## Converters

### Text to ASCII
- pyfiglet — 7 font styles (ansi_shadow, blocky, starwars, banner3, banner4, banner, rounded)
- Support multiple sizes: SMALL, MEDIUM, LARGE
- Color: customizable FG/BG + gradient

### Image to ASCII
- Pillow — resize → pixelate → map ke karakter
- Char map: ` .:-=+*#%@` (light to dark)
- Maintain aspect ratio

### Video/GIF to ASCII
- OpenCV — extract frames
- Process each frame ke ASCII
- Cache frames di server
- Stream frame-by-frame ke overlay

---

## Control Panel Tabs

| Tab | Features |
|-----|----------|
| **DISPLAY** | Manual text, image upload, video upload, clear display |
| **SETTINGS** | Font (7 styles), FG/BG color, gradient, matrix rain, screenshot mode |
| **TIKTOK LIVE** | Connect by username, residential proxy, room ID input |
| **GIFT** | Test animations, blink/duration/speed/sound settings |
| **🤖 AUTO REPLY** | Enable/disable, queue monitor, riddle list, test comment/riddle |

---

## Logging System

Format:
```
[TIMESTAMP] [LEVEL] [SOURCE] message
```

**Levels:** STATUS, EVENT, ERROR, AUTO_REPLY, TTS, TIKTOK

**Indicators:** Status dot (hijau/kuning/merah) di control panel

---

## Tech Stack

- **Backend:** Python Flask + Flask-SocketIO + threading
- **ASCII Rendering:** Pillow (image), opencv (video), pyfiglet (text)
- **TikTok:** TikTokLive v6.6.5 (WebSocket)
- **TTS:** gTTS (server-side, suara cewek)
- **Frontend:** Vanilla JS + CSS, no framework
- **OBS:** Browser Source pointing to overlay.html

---

## Status Indicators

| Status | Color | Meaning |
|--------|-------|---------|
| 🟢 CONNECTED | Hijau | TikTok WS aktif |
| 🟡 CONNECTING | Kuning | Sedang menyambung |
| 🔴 DISCONNECTED | Merah | Putus, auto-retry |
| ⚪ SERVER OFFLINE | Abu | Server mati |

---

## File Structure

```
ascii-art/
├── app.py                   # Flask + Socket.IO + TTS + auto-reply loop
├── app_gift_section.py      # Gift animation server-side
├── tiktok/
│   └── connector.py          # TikTokLive WebSocket (web_proxy/ws_proxy)
├── converters/
│   ├── text.py               # Text → ASCII (pyfiglet)
│   ├── image.py              # Image → ASCII (Pillow)
│   ├── block_art.py          # Block art converter
│   └── blocktext.py          # Block text converter
├── templates/
│   ├── overlay.html          # OBS overlay (canvas + Socket.IO client)
│   ├── control.html          # Streamer control panel (5 tabs)
│   ├── logs.html             # Event logs
│   └── test_ws.html          # WebSocket test page
├── telegram_bot/
│   └── bot.py                # Telegram bot commands
├── static/
├── screenshots/
├── requirements.txt
├── .env.example
└── README.md
```