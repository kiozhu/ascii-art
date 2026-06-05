# ASCII Art Overlay System

Overlay ASCII real-time untuk live streaming (OBS). Flask + Socket.IO powered, integrasi chat TikTok Live, auto-reply AI dengan tebak-tebakan, **RTK (Rush Token Killer)** untuk hemat 70-90% token LLM, animasi gift, suara TTS, matrix rain, screenshot & recording, Control Panel lengkap.

---

## 🚀 Mulai Cepat

### 1. Clone & Install

```bash
git clone git@github.com:kiozhu/ascii-art.git
cd ascii-art
pip install -r requirements.txt
```

### 2. Konfigurasi

```bash
cp .env.example .env
# Edit .env — hanya TELEGRAM_BOT_TOKEN yang wajib; TikTok opsional
```

```env
TELEGRAM_BOT_TOKEN=token_telegram_bot_kamu
```

### 3. Jalankan

```bash
python app.py
```

Buka browser:
- **Overlay:** `http://localhost:5050` (gunakan di OBS)
- **Control Panel:** `http://localhost:5050/control`

---

## 🖥️ Setup OBS

1. Tambah **Browser Source** di OBS
2. URL: `http://localhost:5050` (atau `http://IP_KAMU:5050` untuk remote)
3. Width: `1920`, Height: `1080`
4. CSS:
   ```css
   body { overflow: hidden; margin: 0; padding: 0; background: #000; }
   ```
5. Refresh on launch: **No**

---

## ⚙️ Konfigurasi

Salin `.env.example` ke `.env`:

| Variabel | Wajib | Deskripsi |
|----------|-------|-----------|
| `TELEGRAM_BOT_TOKEN` | Opsional | Token bot Telegram (dapat dari @BotFather) |
| `TELEGRAM_ADMIN_CHAT_ID` | Opsional | Chat ID Telegram kamu (dapat dari @userinfobot) |
| `TELEGRAM_ENABLED` | Opsional | Set `true` untuk aktifkan bot, atau atur via Control Panel |
| `TIKTOK_USERNAME` | Opsional | Username TikTok yang mau di-monitor (tanpa password) |
| `MINIMAX_API_KEY` | Opsional | API key MiniMax untuk auto-reply LLM + tebak-tebakan dinamis |
| `MINIMAX_BASE_URL` | Opsional | Base URL API MiniMax (default: `https://api.minimax.io/anthropic`) |
| `MINIMAX_MODEL` | Opsional | Nama model (`MiniMax-M3` atau `MiniMax-M2.7`, default: `MiniMax-M2.7`) |
| `MINIMAX_ENABLED` | Opsional | Set `true` untuk aktifkan LLM, atau atur via Control Panel |

> **Konfigurasi bot Telegram** — Atur token + chat ID langsung di **Control Panel → Settings → Telegram Bot**. Tidak perlu edit .env manual.

> **Konfigurasi LLM** — Atur API key + model + aktifkan langsung di **Control Panel → Settings → AI Model**. Tidak perlu edit .env manual.

> **Tidak perlu kredensial TikTok** — TikTokLive pakai koneksi WebSocket anonim cukup dengan username.

### Proxy Residensial TikTok (VPS Saja)

Kalau jalan di VPS, TikTok mungkin blokir koneksi karena IP data-center. Tambah proxy residensial:

1. Dapatkan proxy residensial (Bright Data, Oxylabs, SmartProxy)
2. Di **Control Panel → TikTok Live**, masukkan URL proxy:
   ```
   http://user:pass@host:port
   ```
3. Klik **CONNECT**

---

## 🎮 Fitur

### Control Panel (`/control`)

| Tab | Fitur |
|-----|-------|
| **DISPLAY** | Teks manual, upload gambar, bersihkan display |
| **SETTINGS** | Font (7 gaya), warna FG/BG, gradient, matrix rain, mode screenshot, **konfigurasi Bot Telegram**, **konfigurasi AI Model** |
| **TIKTOK LIVE** | Connect by username, support proxy residensial, input room ID |
| **GIFT** | Test animasi, pengaturan blink/durasi/kecepatan/suara |
| **🤖 AUTO REPLY** | Aktifkan/nonaktifkan, monitor antrian, daftar tebak-tebakan, test komentar/tebak-tebakan |

### Integrasi TikTok Live

- **Tampilan gift** — 30+ animasi ASCII art gift (mawar, mahkota, roket, naga, dll.)
- **Komentar chat** — ditampilkan sebagai badge di overlay, masuk ke antrian auto-reply
- **Tampilan username** — ASCII art username dengan efek glitch
- **Animasi robot eyes** — 4 scene per gift
- **Suara TTS** — gTTS membaca username + reply dengan keras

**Connector** — `tiktok/connector.py` membungkus TikTokLive v6.6.5 dengan:
- Propagasi status lengkap: `RESOLVING → CONNECTING → CONNECTED → DISCONNECTED/ERROR/LIVE_ENDED/RETRYING:N/M`
- 9 event handler: CommentEvent, GiftEvent, LikeEvent, FollowEvent, JoinEvent, ShareEvent, ConnectEvent, DisconnectEvent, LiveEndEvent
- Auto-retry dengan exponential backoff (3 percobaan, delay 5s, lebih lama saat rate-limit)
- Deteksi tipe error spesifik: `AlreadyConnected`, `LiveNotFound`, `FailedFetchRoomInfo`, `SignatureRateLimitReached`
- Logger tulis ke stderr (terlihat di console server)
- 5 callback hooks: `on_comment`, `on_gift`, `on_connect(uid, room_id)`, `on_status`, `on_error`, `on_disconnect`, `on_retry`

**Audit nama field** — semua nama field event diverifikasi terhadap `proto/tiktok_proto.py`:
| Event | Field | Path |
|-------|-------|------|
| CommentEvent | username | `event.user_info` (bukan `.user`) |
| CommentEvent | text | `event.content` (bukan `.comment`) |
| GiftEvent | username | `event.from_user` (bukan `.user`) |
| GiftEvent | gift obj | `event.m_gift` (bukan `.gift`) |
| User | name | `user.nick_name` (bukan `.nickname`) |

### Bot Telegram (`/control → Settings → Telegram Bot`)

Atur token bot + admin chat ID langsung dari control panel — tidak perlu edit .env.

Perintah (prefix `ascii`, contoh `/ascii display halo`):

| Perintah | Deskripsi |
|----------|-----------|
| `/ascii display <teks>` | Tampilkan teks di overlay |
| `/ascii big <teks>` | Teks ASCII art besar |
| `/ascii block <teks>` | Teks blok pixel |
| `/ascii half <teks>` | Shading setengah blok |
| `/ascii clear` | Bersihkan overlay |
| `/ascii tiktok <user>` | Connect ke room TikTok |
| `/ascii status` | Status server |
| Teks langsung | Ketik langsung untuk ditampilkan |

Balas foto dengan `/ascii image` untuk kirim ke overlay.

### Auto-Reply AI (Tab 🤖 Auto Reply)

**Integrasi LLM multi-provider** — saat aktif, gunakan MiniMax atau Xiaomi MiMo untuk respons dinamis yang natural:
- **Balas komentar** — generate balasan natural, sesuai konteks (max 5 kata)
- **Generate tebak-tebakan** — buat tebak-tebakan baru secara dinamis (JSON: `{"q": "...", "a": "..."}`)
- Fallback ke pool statis kalau LLM tidak tersedia

**Indikator fallback** — overlay membedakan LLM vs statis secara visual:
- Tag `[AI]` = tebak-tebakan dari LLM (pertanyaan cyan / jawaban emas)
- Tag `[static]` = fallback pool statis (pertanyaan merah / jawaban merah / glow merah)
- TTS menambah "[static]" saat membaca jawaban fallback
- Log menunjukkan `[RIDDLE ASK: [static]]` vs `[RIDDLE ASK: ...]` untuk lacak event fallback

**Sistem tebak-tebakan** — siklus tebak-tebakan background:
- ASK → 5s → ANSWER → 5s → CTA → 5s → tebak-tebakan berikutnya
- 40 tebak-tebakan statis (absurd, logika, budaya, tech) — diganti LLM saat aktif
- Dilewati otomatis saat antrian komentar ada item

**Kebijakan no emoji** — semua output bersih dari emoji:
- Reply LLM di-strip emoji via regex `_remove_emoji()`
- Pool statis (FUNNY_REPLIES) sudah bersih — tanpa emoji
- Label overlay di-strip emoji ("AUTO REPLY" bukan "🤖 AUTO REPLY")
- TTS hanya baca teks bersih

**Balas komentar** — prioritas tertinggi di atas tebak-tebakan:
- Komentar diproses satu-per-satu (tidak batching)
- Tampil 7 detik, tidak overlap dengan tebak-tebakan/CTA

**Pencegahan tabrakan tampilan** — sistem prioritas ketat:

| Sumber | Prioritas | Catatan |
|--------|-----------|---------|
| Auto Reply | 4 (tertinggi) | Komentar masuk — preempt semua |
| Manual Display | 3 | User ketik manual — preempt tebak-tebakan/CTA |
| Riddle ASK/ANSWER | 2 | Preempt CTA saja |
| CTA | 1 (terendah) | Di-preempt oleh semua di atas |

**Pencegahan race condition** — sequence number per-sumber:
- Setiap emit Socket.IO disertai `seq` counter per sumber
- Browser track `window._lastSeq[source]` — event dengan seq lebih rendah di-drop
- Bergaransi urutan satu-per-satu bahkan dengan transport HTTP long-polling
- Serial ketat: **1 reply setiap 7 detik**
- Tidak pernah batching, tidak pernah overlap
- Reply lock dipegang selama durasi tampilan penuh
- 36 reply lucu/sopan (≤5 kata per reply) — diganti LLM saat aktif

**TTS** — gTTS membaca semua fase tebak-tebakan + reply dengan keras

**RTK (Rush Token Killer)** — lapisan optimalisasi token yang duduk antara trigger dan panggilan LLM. Tujuan: kurangi penggunaan token LLM 70-90% tanpa mengorbankan UX.

8 strategi, semua aktif default, semua bisa diatur saat runtime:

| # | Strategi | Default | Tujuan |
|---|----------|---------|--------|
| 1 | Filter panjang minimum | skip LLM untuk <3 char | skip "ok", "🔥", emoji-only |
| 2 | Routing statis-dulu | ON | coba reply statis yang cocok keyword dulu |
| 3 | Cooldown per-user | 30s | 1 reply LLM per user per 30s |
| 4 | Rate limit global | 8 panggilan/menit | hard cap via token bucket |
| 5 | Deteksi duplikat | window 60s, jaccard 0.85 | teks sama/mirip → cache hit |
| 6 | Cache respons | 200 entri LRU | peta (komentar → reply) terkini |
| 7 | Prompt pendek | ON | ~50% token input lebih sedikit |
| 8 | max_tokens dikurangi | ON | 30→20 untuk reply, 60→40 untuk tebak-tebakan |
| + | Throttle tebak-tebakan | jarak 5 menit | 1 tebak-tebakan LLM per 5 menit, sisanya dari pool |

**Monitoring live** — `GET /api/rtk/stats` mengembalikan:
```json
{
  "stats": {"llm_calls": 2, "llm_skipped": 3, "llm_cached": 0, "static_used": 0},
  "summary": {"llm_calls_baseline": 5, "llm_calls_made": 2, "llm_calls_saved": 3, "savings_pct": 60.0},
  "calls_in_last_minute": 2, "cache_size": 0
}
```

**Atur saat runtime** — `POST /api/rtk/config`:
```json
// Aggresif (hemat token):
{"rtk_per_user_cooldown_sec": 60, "rtk_global_rate_per_min": 4}
// Santai (LLM lebih sering):
{"rtk_per_user_cooldown_sec": 10, "rtk_global_rate_per_min": 20}
// Nonaktifkan total:
{"rtk_enabled": false}
```

**Reset** — `POST /api/rtk/reset` bersihkan semua cache dan counter.

---

## 📁 Struktur Proyek

```
ascii-art/
├── app.py                  # Flask + Socket.IO + TTS + loop auto-reply
├── app_gift_section.py     # Animasi gift sisi server
├── tiktok/
│   └── connector.py        # Connector WebSocket TikTokLive (web_proxy/ws_proxy)
├── converters/
│   ├── text.py             # Teks → ASCII
│   ├── image.py            # Gambar → ASCII (Pillow)
│   └── blocktext.py        # Teks blok
├── templates/
│   ├── overlay.html         # Overlay OBS (canvas + client Socket.IO)
│   ├── control.html        # Panel kontrol streamer (5 tab)
│   └── logs.html           # Log event
├── telegram_bot/
│   └── bot.py              # Perintah bot Telegram
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🛠️ Tech Stack

- **Flask** + **Socket.IO** — server web real-time & WebSocket
- **pyfiglet** — render teks ASCII
- **TikTokLive** — WebSocket chat TikTok live (v6.6.5)
- **gTTS** — Google text-to-speech (sisi server, suara cewek)
