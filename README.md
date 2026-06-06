# 🎮 ASCII Art Overlay — TikTok Live Auto-Reply

Overlay ASCII art untuk TikTok Live dengan auto-reply AI, tebak-tebakan dinamis, gift animation, dan TTS.

## ✨ Fitur

### 🤖 Auto-Reply AI
- Balas komentar secara otomatis menggunakan LLM (Xiaomi MiMo / MiniMax)
- Reply natural dalam Bahasa Indonesia (max 8 kata)
- Anti-spam: duplikat komentar, limit per user, cooldown

### 🎯 Tebak-Tebakan Dinamis
- Generate tebak-tebakan lucu via LLM (pre-queue, tidak berulang)
- Fallback ke static pool (67+ riddle) kalau LLM timeout
- Siklus: Tanya → Jawab → CTA (60 detik interval)

### 🎁 Gift Animation
- Animasi robot eye + "terima kasih @username" untuk setiap gift
- TTS: suara terima kasih saat gift masuk
- Interleaving: gift ↔ comment selang-seling
- Anti-spam gift: 3 detik cooldown (30 detik untuk user sama)

### 🔊 TTS (Text-to-Speech)
- Suara untuk setiap reply, riddle, dan gift
- Queue system: hanya 1 TTS bermain pada satu waktu
- Sinkron dengan display (tidak telat/kecepetan)

### 🎨 Display Gradient
- Warna gradasi dari control panel (tidak hardcoded)
- Semua display: auto-reply, riddle, CTA, gift → pakai gradient
- Persist setelah refresh (tidak hilang)

### 🛠️ System Tools
- Hapus cache manual dari control panel
- Hapus queue manual dari control panel
- .env management dari control panel
- Auto-clear queue saat disconnect

### 🔄 Auto-Start
- Auto-enable LLM dari `.env` saat startup
- Auto-connect TikTok dari `.env` saat startup
- Auto-enable auto-reply dari `.env` saat startup
- Data persisten di `data/.env.local` + `data/runtime_state.json`

## 🚀 Cara Pakai

### 1. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Setup `.env`
```env
# TikTok
TIKTOK_USERNAME=rach.ai

# LLM (Xiaomi MiMo)
XIAOMI_API_KEY=sk-***
XIAOMI_MODEL=mimo-v2.5-pro
XIAOMI_ENABLED=true

# Telegram (opsional)
TELEGRAM_BOT_TOKEN=***
TELEGRAM_CHAT_ID=***
TELEGRAM_ENABLED=true

# Auto-reply
AUTO_REPLY_ENABLED=true
```

### 3. Jalankan Server
```bash
python app.py
```

Server otomatis:
- Enable LLM dari `.env`
- Connect ke TikTok dari `TIKTOK_USERNAME`
- Start auto-reply + riddle cycle
- Pre-fill riddle queue dari LLM

### 4. Buka Control Panel
```
http://localhost:5050/control
```

Fitur control panel:
- 🎨 Pengaturan display (font, warna, gradient)
- 🤖 Konfigurasi LLM (API key, model)
- 📱 Konfigurasi TikTok (username, connect/disconnect)
- 🎁 Pengaturan gift (animasi, suara)
- 🛠️ System tools (hapus cache, hapus queue, lihat .env)

### 5. Buka Overlay
```
http://localhost:5050/
```

Tambahkan sebagai Browser Source di OBS:
- URL: `http://localhost:5050/`
- Width: 1920, Height: 1080
- ✅ Shutdown source when not visible

## 📡 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/status` | GET | Status server + TikTok + LLM |
| `/api/settings` | GET | Pengaturan display |
| `/api/settings/update` | POST | Update pengaturan |
| `/api/tiktok/connect` | POST | Connect ke TikTok Live |
| `/api/tiktok/disconnect` | POST | Disconnect + clear queue |
| `/api/tiktok/simulate` | POST | Simulate comment/gift |
| `/api/llm/config` | POST | Konfigurasi LLM |
| `/api/llm/models` | GET | Daftar model LLM |
| `/api/clear_cache` | POST | Hapus semua cache |
| `/api/clear_queue` | POST | Hapus comment + gift queue |
| `/api/env` | GET | Baca .env (key masked) |
| `/api/env/update` | POST | Update .env |

## 🏗️ Arsitektur

```
┌─────────────────────────────────────────────┐
│  TikTok Live (piratetok-live-py)            │
│  └── Comment → on_comment()                 │
│  └── Gift → on_gift()                       │
├─────────────────────────────────────────────┤
│  Auto-Reply Loop                            │
│  └── Gift Queue (max 30) → Gift Display     │
│  └── Comment Queue (max 12) → LLM Reply     │
│  └── Riddle Queue (LLM pre-gen) → Riddle    │
├─────────────────────────────────────────────┤
│  Display Layer (Socket.IO)                  │
│  └── auto_reply_display (priority 4)        │
│  └── riddle_display (priority 2)            │
│  └── cta_display (priority 1)               │
│  └── gift_display (separate box)            │
├─────────────────────────────────────────────┤
│  TTS Queue (1 at a time)                    │
│  └── Edge TTS → Browser Audio               │
└─────────────────────────────────────────────┘
```

## ⚙️ Konfigurasi

### LLM Providers
| Provider | Model | API Format |
|----------|-------|------------|
| Xiaomi MiMo | mimo-v2.5-pro | OpenAI-compatible |
| Xiaomi MiMo | mimo-v2.5-flash | OpenAI-compatible |
| MiniMax | MiniMax-M2.7 | Anthropic |

### Queue Limits
| Queue | Max | Drop Policy |
|-------|-----|-------------|
| Comment | 12 | Drop oldest |
| Gift | 30 | Drop oldest |
| Riddle | 3 | Pre-gen LLM |

### Timing
| Setting | Default | Deskripsi |
|---------|---------|-----------|
| reply_display_sec | 9 | Durasi display reply |
| riddle_interval_sec | 10 | Interval antar riddle |
| idle_timeout_sec | 60 | Timeout sebelum riddle baru |
| gift_cooldown | 3s/30s | Anti-spam gift |

## 📝 License

MIT License
