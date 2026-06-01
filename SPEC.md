# ASCII Overlay — Live Streaming System

## Concept & Vision

Sistem overlay interaktif untuk live streaming yang mengubah teks, gambar, GIF, dan video menjadi tampilan ASCII art real-time. Mengadopsi gaya terminal futuristik / Matrix — hijau neon di atas hitam, kesan hacker futuristik. Ditampilkan via OBS Browser Source, membuat live coding / AI / teknologi terlihat jauh lebih menarik.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Flask Server                      │
│                                                     │
│  ┌──────────────┐  WebSocket  ┌─────────────────┐  │
│  │ Control Panel │◄──────────►│   Overlay View   │  │
│  │ (streamer)    │             │ (OBS Browser Src)│  │
│  └──────────────┘             └─────────────────┘  │
│         │                                         │
│         ▼                                         │
│  ┌──────────────┐  ┌────────────────────────┐     │
│  │ Logs Dashboard│  │ TikTok WS Connector   │     │
│  └──────────────┘  └────────────────────────┘     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Port:** 5050 (Flask + WebSocket)

**3 Interfaces:**
- `overlay.html` — Tampilan live (OBS Browser Source)
- `control.html` — Panel kontrol streamer
- `logs.html` — Monitoring & log

---

## Visual Identity

- **Dominan:** Hitam `#000` + hijau neon `#00ff41`
- **Font:** Monospace (Courier New / Fira Code)
- **Style:** Terminal / Matrix / Cyberpunk
- **Effects:** Matrix rain background, glow effects, flicker

---

## Area Display

### 1. Manual Display Box
Dikendalikan penuh oleh streamer:
- Teks → ASCII art besar
- Gambar → ASCII representation
- GIF/Video → ASCII animation loop

### 2. Live Event Box (Auto)
Otomatis dari TikTok live comments:
- Username terbaru ditampilkan sebagai ASCII
- Tidak ada antrian — langsung replace
- Lama tampil: 5 detik, lalu fade

---

## TikTok Integration

**Method:** TikTok WebSocket (unofficial reverse-engineering)
- Connect ke live stream via room ID
- Listen untuk comment events
- Parse username + comment text
- Relay ke overlay via WebSocket

**Status flow:**
```
Server Starting → Connecting → Connected → Live
                                        ↘ Disconnected → Reconnecting...
```

---

## Converters

### Text to ASCII
- ASCII art dari teks (bebas pakai library/figlet)
- Support multiple sizes: SMALL, MEDIUM, LARGE
- Color: hijau neon dengan glow

### Image to ASCII
- Load image → resize → pixelate → map ke karakter
- Char map: ` .:-=+*#%@` (light to dark)
- Maintain aspect ratio

### Video/GIF to ASCII
- Extract frames (FFmpeg)
- Process each frame ke ASCII
- Cache frames di server
- Stream frame-by-frame ke overlay

---

## Logging System

Setiap aktivitas dicatat dengan timestamp:
- `STATUS` — koneksi server, TikTok, WebSocket
- `EVENT` — komentar masuk, media upload, display change
- `ERROR` — kesalahan koneksi, processing

Format:
```
[TIMESTAMP] [LEVEL] [SOURCE] message
```

**Indicators:** Status dot (hijau/kuning/merah) di control panel

---

## File Structure

```
ASCII-Art/
├── SPEC.md
├── app.py                    # Flask + WebSocket server
├── requirements.txt
├── converters/
│   ├── text.py
│   ├── image.py
│   └── video.py
├── tiktok/
│   └── connector.py          # TikTok WS connection
└── static/
    └── matrix.js             # Matrix rain effect
overlay.html                   # OBS view (main)
control.html                   # Streamer control
logs.html                      # Dashboard logs
```

---

## Tech Stack

- **Backend:** Python Flask + Flask-SocketIO
- **ASCII Rendering:** Pillow (image), opencv (video), figlet (text)
- **TikTok:** WebSocket client (playwright/websockets)
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

## Future Expansions

- Twitch / YouTube Live / Kick integration
- Gift notification ASCII art
- Leaderboard interaksi
- AI auto-ASCII berdasarkan topik live