"""
ASCII Overlay - Flask + SocketIO Server
========================================
Serves 3 pages:
  /              → overlay.html (OBS view)
  /control       → control.html (streamer panel)
  /logs          → logs.html (monitoring)

WebSocket events:
  tiktok_comment → relay username to overlay
  display_manual → manual content to overlay
  status_update  → connection status broadcast
  media_upload   → image/gif/video processing
"""

from dotenv import load_dotenv
load_dotenv()

import os
import re
import base64
import uuid
import json
import time
import random
import pyfiglet
import threading
from datetime import datetime
import requests
from gtts import gTTS
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from converters.text import text_to_ascii
from converters.blocktext import block_render, block_half
from converters.block_art import get_hermes_art

app = Flask(__name__)
CORS(app)
app.config["SECRET"] = "ascii-overlay-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ─── TTS VOICE ─────────────────────────────────────────────────
AUDIO_CACHE_DIR = "/tmp/tts_cache"
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

def speak_text(text, lang="id"):
    """Generate MP3 from text via gTTS, save to cache, return filename"""
    try:
        safe_key = text.replace(" ", "_")[:30]
        cache_file = f"{AUDIO_CACHE_DIR}/{safe_key}_{hash(text) % 100000}.mp3"
        if not os.path.exists(cache_file):
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(cache_file)
        return cache_file
    except Exception as e:
        log("WARN", "TTS", f"TTS failed: {e}")
        return None

def emit_tts_audio(text, lang="id"):
    """Read MP3 file and emit as base64 audio event via SocketIO"""
    path = speak_text(text, lang)
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            mp3_data = f.read()
        b64 = base64.b64encode(mp3_data).decode()
        # Emit to all connected clients
        socketio.emit("tts_audio", {
            "text": text,
            "audio": b64,
            "mime": "audio/mpeg"
        })
        log("INFO", "TTS", f"Emitted TTS: {text[:30]}")
    except Exception as e:
        log("WARN", "TTS", f"emit_tts_audio failed: {e}")

def speak_async(text, lang="id"):
    """Speak text in background thread - emit to browser instead of local play"""
    threading.Thread(target=lambda: emit_tts_audio(text, lang), daemon=True).start()

def speak_and_cleanup(text, lang):
    pass  # No local playback anymore

# ─── LOGGING ───────────────────────────────────────────────
import logging as _logging

_logging.basicConfig(
    level=_logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        _logging.FileHandler("/tmp/ascii-app.log"),
        _logging.StreamHandler(),
    ],
)
_logger = _logging.getLogger("ascii")

def log(level, source, msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [{level}] [{source}] {msg}"
    _logger.info(f"[{source}] {msg}")
    # store in memory for log page
    LOGS.append({"ts": ts, "level": level, "source": source, "msg": msg})
    if len(LOGS) > 500:
        LOGS.pop(0)

LOGS = []

# ─── STATE ─────────────────────────────────────────────────
state = {
    "server_status": "STARTING",
    "tiktok_status": "DISCONNECTED",
    "tiktok_unique_id": None,
    "tiktok_room_id": None,
    "overlay_content": None,
    "manual_content": None,
    "event_count": 0,
    "live_id": None,
    "active_display": None,  # {content, type} - konten yang sedang aktif display
    # Per-source sequence counters for ordering/dedup — incremented before each emit
    "seq": {"manual": 0, "auto_reply": 0, "riddle": 0, "cta": 0},
}

# ─── SETTINGS ────────────────────────────────────────────────
# ─── GIFT ART ─────────────────────────────────────────────────
# Each gift type has an ASCII art banner + optional sound cue
# Art style: similar to Hermes /skin banners — ornate, dramatic, colorful

GIFT_ARTS = {
    "rose": {
            "emoji": "🌹",
            "title": "Rose",
            "art": (
    "[bold #FF1493]    ⣿⣿⣿⣿⣿⣿⣼    \n" +
    "[#FF69B4]  ⣿⣿⣟⣿⣟⣿⣟⣿⣟⣿  \n" +
    "[#FF1493] ⣿⣿⣟⣿⣿⣿⣿⣿⣿⣿⣟⣿ \n" +
    "[#FF69B4] ⣿⣿⣟⣿⠿⠿⠿⠿⠿⣿⣟⣿ \n" +
    "[#FF1493] ⣿⣿⣟            \n" +
    "[#FF69B4]  ⣿⣿⣟          \n" +
    "[#FF1493]   ⣿⣿⠿        \n" +
    "[#FF69B4]    ⣿⠿         "
    ),
            "sound": "rose",
        },

        "crown": {
            "emoji": "👑",
            "title": "Crown",
            "art": (
    "[bold #FFD700]   ⣿⣿⣼     \n" +
    "[#FFBF00]  ⣿⣿⠿      \n" +
    "[#FFD700] ⣿⠿         \n" +
    "[#FFBF00] ⣿           \n" +
    "[#FFD700] ⣿           \n" +
    "[#FFBF00] ⣿           \n" +
    "[#FFD700] ⣿           \n" +
    "[#FFBF00] ⣿           "
    ),
            "sound": "crown",
        },

        "heart": {
            "emoji": "❤",
            "title": "Heart",
            "art": (
    "[bold #FF0000]  ⣿⣿⣼  \n" +
    "[#FF4444] ⣿⠿⠿  \n" +
    "[#FF0000] ⣿      \n" +
    "[#FF4444] ⣿      \n" +
    "[#FF0000] ⣿      \n" +
    "[#FF4444] ⣿      \n" +
    "[#FF0000]       \n" +
    "[#FF4444]       "
    ),
            "sound": "heart",
        },

        "diamond": {
            "emoji": "💎",
            "title": "Diamond",
            "art": (
    "[bold #00FFFF]    ⣿    \n" +
    "[#00CED1]   ⣿⠿   \n" +
    "[#00FFFF]  ⣿   \n" +
    "[#00CED1] ⣿     \n" +
    "[#00FFFF]⣿      \n" +
    "[#00CED1] ⣿     \n" +
    "[#00FFFF]  ⣿   \n" +
    "[#00CED1]   ⣿  "
    ),
            "sound": "diamond",
        },

        "dragon": {
            "emoji": "🐉",
            "title": "Dragon",
            "art": (
    "[bold #FF4500] ⣿⠿    \n" +
    "[#FF6347]  ⣿    \n" +
    "[#FF4500]   ⣿  \n" +
    "[#FF6347]  ⣿⠿ \n" +
    "[#FF4500] ⣿ ⣿  \n" +
    "[#FF6347]⣿  ⣿ \n" +
    "[#FF4500]   ⣿ \n" +
    "[#FF6347]   ⣿ "
    ),
            "sound": "dragon",
        },

        "fortune": {
            "emoji": "🍀",
            "title": "Fortune",
            "art": (
    "[bold #00FF7F]  ⣿   \n" +
    "[#7FFF00] ⣿⠿  \n" +
    "[#00FF7F]⣿   \n" +
    "[#7FFF00] ⣿⠿ \n" +
    "[#00FF7F]  ⣿  \n" +
    "[#7FFF00]     \n" +
    "[#00FF7F]     \n" +
    "[#7FFF00]     "
    ),
            "sound": "fortune",
        },

        "plane": {
            "emoji": "✈️",
            "title": "Plane",
            "art": (
    "[bold #87CEEB]⣼       \n" +
    "[#ADD8E6] ⣿     \n" +
    "[#87CEEB]  ⣿   \n" +
    "[#ADD8E6]   ⣿ \n" +
    "[#87CEEB]    ⣿\n" +
    "[#ADD8E6]   ⣿ \n" +
    "[#87CEEB]  ⣿   \n" +
    "[#ADD8E6]       "
    ),
            "sound": "plane",
        },

    "music": {
        "emoji": "🎵",
        "title": "Music",
        "art": (
"[bold #9370DB]████████╗██╗  ██╗███████╗    ███████╗███████╗ ██████╗ █████╗ ██████╗ ███████╗" +
"" +
"[#BA55D3]╚══██╔══╝██║  ██║██╔════╝    ██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝" +
"" +
"[#9370DB]   ██║   ███████║█████╗      █████╗  ███████╗██║     ███████║██████╔╝█████╗" +
"" +
"[#BA55D3]   ██║   ██╔══██║██╔══╝      ██╔══╝  ╚════██║██║     ██╔══██║██╔═══╝ ██╔══╝" +
"" +
"[#9370DB]   ██║   ██║  ██║███████╗    ███████╗███████║╚██████╗██║  ██║██║     ███████╗" +
"" +
"[#BA55D3]   ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚══════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝     ╚══════╝"
),
        "sound": "music",
    },

    "star": {
        "emoji": "⭐",
        "title": "Star",
        "art": (
"[bold #FFFF00]████████╗██╗  ██╗███████╗    ███████╗███████╗ ██████╗ █████╗ ██████╗ ███████╗" +
"" +
"[#FFD700]╚══██╔══╝██║  ██║██╔════╝    ██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝" +
"" +
"[#FFFF00]   ██║   ███████║█████╗      █████╗  ███████╗██║     ███████║██████╔╝█████╗" +
"" +
"[#FFD700]   ██║   ██╔══██║██╔══╝      ██╔══╝  ╚════██║██║     ██╔══██║██╔═══╝ ██╔══╝" +
"" +
"[#FFFF00]   ██║   ██║  ██║███████╗    ███████╗███████║╚██████╗██║  ██║██║     ███████╗" +
"" +
"[#FFD700]   ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚══════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝     ╚══════╝"
),
        "sound": "star",
    },

    "rocket": {
        "emoji": "🚀",
        "title": "Rocket",
        "art": (
"[bold #FF6347]████████╗██╗  ██╗███████╗    ███████╗███████╗ ██████╗ █████╗ ██████╗ ███████╗" +
"" +
"[#FF7F50]╚══██╔══╝██║  ██║██╔════╝    ██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝" +
"" +
"[#FF6347]   ██║   ███████║█████╗      █████╗  ███████╗██║     ███████║██████╔╝█████╗" +
"" +
"[#FF7F50]   ██║   ██╔══██║██╔══╝      ██╔══╝  ╚════██║██║     ██╔══██║██╔═══╝ ██╔══╝" +
"" +
"[#FF6347]   ██║   ██║  ██║███████╗    ███████╗███████║╚██████╗██║  ██║██║     ███████╗" +
"" +
"[#FF7F50]   ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚══════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝     ╚══════╝"
),
        "sound": "rocket",
    }
}



# Gift thank-you message art (line-by-line typing animation)
# Each gift has a dramatic thank-you banner in ASCII art style
GIFT_MESSAGES = {
    "rose": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  🌹  Mawar  🌹  *.         ║[/]",
        "[bold #FFD700]║         *  .  🌹  .  *           ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "crown": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  👑  Mahkota  👑  *.       ║[/]",
        "[bold #FFD700]║         *  .  👑  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "heart": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  ❤️  Hati  ❤️  *.          ║[/]",
        "[bold #FFD700]║         *  .  ❤️  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "diamond": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  💎  Berlian  💎  *.      ║[/]",
        "[bold #FFD700]║         *  .  💎  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "dragon": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  🐉  Naga  🐉  *.          ║[/]",
        "[bold #FFD700]║         *  .  🐉  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "fortune": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  🎁  Fortuna  🎁  *.       ║[/]",
        "[bold #FFD700]║         *  .  🎁  .  *             ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "plane": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  ✈️  Pesawat  ✈️  *.        ║[/]",
        "[bold #FFD700]║         *  .  ✈️  .  *             ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "music": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  🎵  Musik  🎵  *.         ║[/]",
        "[bold #FFD700]║         *  .  🎵  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "star": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  ⭐  Bintang  ⭐  *.       ║[/]",
        "[bold #FFD700]║         *  .  ⭐  .  *             ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
    "rocket": [
        "[bold #FFD700]╭══════════════════════════════════╮[/]",
        "[bold #FFD700]║     .*  🚀  Roket  🚀  *.         ║[/]",
        "[bold #FFD700]║         *  .  🚀  .  *            ║[/]",
        "[bold #FFD700]║   ─────────────────────────────  ║[/]",
        "[bold #FFD700]║         TERIMAKASIH              ║[/]",
        "[bold #FFD700]║           @Kiozhu                ║[/]",
        "[bold #FFD700]╰══════════════════════════════════╯[/]",
    ],
}

# Default thank-you message template
DEFAULT_GIFT_MESSAGE = "Terima kasih @{username} untuk {gift_emoji} {gift_name}!"
DEFAULT_GIFT_SOUND = "on"  # "on" or "off"
DEFAULT_GIFT_TYPING_SPEED = 50  # ms per character
DEFAULT_GIFT_BLINK_DURATION = 800  # ms
DEFAULT_GIFT_DISPLAY_DURATION = 5000  # ms

# ─── AUTO REPLY (AI Chat) SETTINGS ──────────────────────────
auto_reply_settings = {
    "enabled": False,
    "idle_timeout_sec": 5,
    "riddle_interval_sec": 5,
    "max_words": 5,
    "reply_style": "funny",
    "reply_display_sec": 7,
    # MiniMax LLM config (runtime-configurable via /api/llm/config)
    "llm_enabled": False,
    "llm_api_key": "",
    "llm_group_id": "",
    "llm_model": "MiniMax-M2.7",
    "llm_base_url": "https://api.minimax.io/anthropic",
    # ── RTK (Rush Token Killer) settings ──
    # Goal: cut LLM token usage 70-90% while keeping UX smooth.
    "rtk_enabled": True,
    "rtk_per_user_cooldown_sec": 30,    # same user = 1 LLM reply per Ns
    "rtk_global_rate_per_min": 8,       # max LLM calls per minute total
    "rtk_duplicate_window_sec": 60,     # same comment text within Ns = cache hit
    "rtk_dup_similarity_thresh": 0.85,  # jaccard ratio for "same-ish" comments
    "rtk_cache_max": 200,               # max entries in LLM response cache
    "rtk_min_comment_len": 3,           # skip LLM for <3 char comments (emoji, "ok")
    "rtk_static_first": True,           # try static reply first; LLM only if no match
    "rtk_short_prompts": True,          # use compact prompts (saves ~50% input tokens)
    "rtk_reduce_max_tokens": True,      # 30→20 for reply, 60→40 for riddle
}

LLM_MODELS = [
    {"id": "MiniMax-M3",      "name": "MiniMax M3 (latest)",          "desc": "Flagship, 1M context, coding & multimodal"},
    {"id": "MiniMax-M2.7",    "name": "MiniMax M2.7",                 "desc": "Fast, ideal for auto-reply"},
]

# ─── RIDDLE POOL ─────────────────────────────────────────────
# Each riddle is a dict with {question, answer} — max ~5 words each
RIDDLES = [
    {"q": "Kenapa ayam nyebrang jalan?", "a": "Karena belum ada ojol"},
    {"q": "Benda apa yang makin kecil makin besar?", "a": "Lubang"},
    {"q": "Kenapa programmer suka gelap?", "a": "Karena butuh night mode"},
    {"q": "Apa yang punya kaki tapi gak bisa jalan?", "a": "Meja"},
    {"q": "Telor rebus = telor apa?", "a": "Telor yang udah matang"},
    {"q": "Kenapa GPS suka gagal?", "a": "Karena signal ilang"},
    {"q": "HP apa yang bikin kesel?", "a": "HP lowbat"},
    {"q": "Kaca apa yang bikin pusing?", "a": "Kacamata"},
    {"q": "Ikan apa yang bikin lapar?", "a": "Ikan teri"},
    {"q": "Bantal apa yang bikin ngantuk?", "a": "Bantal"},
    {"q": "Kursi apa yang bikin pusing?", "a": "Kursi putar"},
    {"q": "WiFi apa yang bikin galau?", "a": "WiFi error"},
    {"q": "Mouse apa yang bunyi terus?", "a": "Mouse eror"},
    {"q": "Speaker apa yang bikin tinggi?", "a": "Speaker ngebass"},
    {"q": "CPU apa yang bikin meledak?", "a": "CPU overload"},
    {"q": "RAM apa yang bikin lupa?", "a": "RAM penuh"},
    {"q": "Code apa yang bikin kesel?", "a": "Code error"},
    {"q": "Loop apa yang bikin pusing?", "a": "Loop infinity"},
    {"q": "Bug apa yang bikin semangat?", "a": "Bug found"},
    # Campur: absurd + logika + budaya
    {"q": "Apa yang ditulis tangan tapi gak bisa dibaca?", "a": "Tinta kosong"},
    {"q": "Benda apa yang kalau dioven malah mengeras?", "a": "Telor"},
    {"q": "Kenapa matahari terbit dari timur?", "a": "Karena barat gak mau"},
    {"q": "Kaki ada 4 tapi satu arah, apa itu?", "a": "Kursi"},
    {"q": "Apa yang makin banyak dimakan makin kecil?", "a": "Gula"},
    {"q": "Telur yang dikeluarin dari sarang = apa?", "a": "Telur mentah"},
    {"q": "Kenapa uang kertas punya angka?", "a": "Supaya tau nilainya"},
    {"q": "Kalau dipotong malah jadi panjang, apa itu?", "a": "Waktu"},
    {"q": "Botol kosong tapi ringan, kenapa?", "a": "Isinya angin"},
    {"q": "Bedanya sama dan beda apa?", "a": "Satu huruf"},
    {"q": "Apa yang punya kepala tapi gak punya otak?", "a": "Bantal"},
    {"q": "Kenapa kucing takut cucumber?", "a": "Klenik"},
    {"q": "Kalau kamu punya 3 apel, dibagi 4 orang, jadi apa?", "a": "4"},
    {"q": "Apa yang bau tapi bukan bau?", "a": "Mawar"},
    {"q": "Matahari terbenam, bintang belum keluar, apa itu?", "a": "Senja"},
    {"q": "Kalau ditulis salah jadi benar, apa itu?", "a": "Salah ketik"},
    {"q": "Sebutkan 5 buah yang sama semua!", "a": "Mangga"},
    {"q": "Kenapa komputer sering lupa?", "a": "Karena RAM kecil"},
    {"q": "Apa yang makin dikecilin makin gedek?", "a": "Kipas"},
    {"q": "Kapan manusia bicara tanpa mulut?", "a": "Chat"},
    {"q": "Kenapa mobil gak pernah mager?", "a": "Karena ban rotate"},
    {"q": "Jambu apa yang bisa terbang?", "a": "Jambon"},
]

# ─── CTA / SARAN KOMENTAR ─────────────────────────────────────
# Diselingi antara tebak-tebakan, supaya ga monoton
CTAS = [
    "Mau tau jawaban? Ketik di kolom komentar ya! 👇",
    "Kirim jawaban kamu di komentar dong! 😄",
    "Coba tebak! Tulis di komentar 👇",
    "Gas jawab di kolom komentar! 👇",
    "Kirim jawaban terbaikmu di kolom komentar!",
    "Ayoo coba tebak, ketik jawaban di kolom komentar! 🙌",
    "Kalo tau jawabannya, tulis di komentar ya! 👇",
    "Gausah malu, ketik jawaban di komentar! 😎",
    "Tebak dulu, baru ketik jawaban! 👇",
    "Yang tau langsung tulis di kolom komentar! 💪",
    "Chat di kolom bawah ya, jangan malu! 😂",
    "Ketik jawaban kamu di komentar, cepetan! ⏰",
    "Ayam nyebrang dulu ya... eh maksudnya ketik jawaban! 🐔",
    "Jgn lupa ketik jawaban di kolom komentar 👇",
    "Siapa dulu yg tau? Coba ketik di komentar! 😄",
    "Ketik jawaban terbaikmu di kolom komentar! 🙌",
    "Gas ketik jawabanmu di kolom komentar! 😂",
    "ayo tulis jawabanmu di kolom komentar! 👇",
    "siapa yg tau? ketik di kolom komentar 💬",
]

# Auto reply internal state
auto_reply_state = {
    "comment_queue": [],        # list of (username, comment) pending processing
    "last_comment_time": 0,     # timestamp of last comment
    "current_riddle": None,     # {"q": ..., "a": ..., "ask_time": ...}
    "riddle_timer": None,       # threading.Timer for next riddle action
    "loop_thread": None,        # background processing thread
    "running": False,
    "riddle_locked": False,     # True during riddle ASK→ANS→CTA cycle, queues comments
    "reply_locked": False,      # True while a reply is being displayed (prevents next reply)
    "reply_done_time": 0,       # timestamp when current reply display ends
    # ── RTK state ──
    "rtk_per_user_last_llm": {},        # {username_lower: last_llm_ts}
    "rtk_recent_comments": [],          # [(ts, normalized_text)]
    "rtk_llm_call_timestamps": [],      # [ts, ts, ...] (last 60s)
    "rtk_response_cache": {},           # {comment_key: {"reply": str, "ts": ts}}
    "rtk_last_riddle_llm_ts": 0,        # when we last called LLM for a riddle
    "rtk_stats": {                      # exposed via /api/status for monitoring
        "llm_calls": 0, "llm_skipped": 0, "llm_cached": 0,
        "static_used": 0, "tokens_saved_estimate": 0,
    },
}

# Funny reply templates (max 5 words each, NO emoji)
FUNNY_REPLIES = [
    "Kreatif juga nih",
    "Hah serius nih",
    "Kok bisa gitu sih",
    "Level tinggi banget",
    "Yakin check lagi deh",
    "Kagum abis nih",
    "Keren abis gak sih",
    "Auto nangis aku",
    "WAIT APA",
    "KAMU NIH PASTI",
    "Wah benar juga",
    "Lebay banget dah",
    "Gas terus bang",
    "KALAU BENER INI GILA",
    "Makasih participate",
    "PING PONG",
    "Gak paham tapi oke",
    "Bro level berapa",
    "Mantap jiwa bang",
    "KODE RED",
    "NOTED",
    "AUTO LIKE",
    "WAW KEREN BANGET",
    "SAD BOYS",
    "GAMERS ONLY",
    "NO COMMENTS",
    "WAIT WAIT WAIT",
    "FIX TIE",
    "BENER BANGET TU",
    "PANIK GANS",
    "FIX INI YANG BENER",
]


def call_minimax(prompt, max_words=5):
    """Call MiniMax LLM API and return response text."""
    api_key = auto_reply_settings.get("llm_api_key", "").strip()
    base_url = auto_reply_settings.get("llm_base_url", "https://api.minimax.io/anthropic").strip().rstrip("/")
    model = auto_reply_settings.get("llm_model", "MiniMax-M2.7")

    if not api_key:
        return None

    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # RTK: optionally reduce max_tokens from 30→20
    mt = 20 if auto_reply_settings.get("rtk_reduce_max_tokens") else 30
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": mt,
        "temperature": 0.9,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Trim to max_words
        words = text.strip().split()
        if len(words) > max_words:
            text = " ".join(words[:max_words])
        return text.strip()
    except Exception as e:
        print(f"[MiniMax] LLM call failed: {e}")
        return None


# ─── RTK: RUSH TOKEN KILLER ──────────────────────────────────
# Token-optimization layer that sits BETWEEN the trigger and the LLM call.
# Goal: cut LLM token usage 70-90% without harming UX.
#
# Strategies (all independent, all on by default):
#   1. Min-length filter      — skip LLM for tiny/emoji comments
#   2. Static-first routing   — only call LLM when no context match
#   3. Per-user cooldown      — 1 LLM reply per user per Ns
#   4. Global token bucket    — max N LLM calls per minute
#   5. Duplicate detection    — same/similar comment within Ns = cache hit
#   6. Response cache         — recent (comment_key) → reply
#   7. Short prompts          — use compact prompt when rtk_short_prompts=True
#   8. Reduced max_tokens     — fewer output tokens per call
#
# All counters are exposed via /api/status → rtk_stats for live monitoring.

_RTK_LOCK = threading.Lock()


def _rtk_normalize(text):
    """Lowercase, strip punctuation, collapse whitespace — for dedup hashing."""
    import re as _re
    s = (text or "").lower()
    s = _re.sub(r"[^a-z0-9\u00C0-\u017F\s]", " ", s)  # keep alnum + Latin-1 letters
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def _rtk_jaccard(a, b):
    """Word-level Jaccard similarity in [0, 1]."""
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _rtk_should_call_llm(username, comment):
    """Decide whether to call the LLM for this (username, comment).
    Returns (allow: bool, reason: str, cached_reply: str|None).
    Side-effect: trims expired entries from rtk_* lists.
    Thread-safe via _RTK_LOCK.
    """
    if not auto_reply_settings.get("rtk_enabled", True):
        return True, "rtk_disabled", None

    with _RTK_LOCK:
        now = time.time()
        stats = auto_reply_state["rtk_stats"]
        comment_norm = _rtk_normalize(comment)
        uname = (username or "").strip().lower()

        # ── 1. Min-length filter ──
        min_len = auto_reply_settings.get("rtk_min_comment_len", 3)
        if len(comment_norm) < min_len:
            stats["llm_skipped"] += 1
            stats["tokens_saved_estimate"] += 50
            return False, "too_short", None

        # ── 2. Per-user cooldown ──
        cooldown = auto_reply_settings.get("rtk_per_user_cooldown_sec", 30)
        if uname:
            last = auto_reply_state["rtk_per_user_last_llm"].get(uname, 0)
            if now - last < cooldown:
                stats["llm_skipped"] += 1
                stats["tokens_saved_estimate"] += 80
                return False, "user_cooldown", None

        # ── 3. Global rate limit (token bucket) ──
        per_min = auto_reply_settings.get("rtk_global_rate_per_min", 8)
        # Trim timestamps older than 60s
        cutoff = now - 60
        auto_reply_state["rtk_llm_call_timestamps"] = [
            t for t in auto_reply_state["rtk_llm_call_timestamps"] if t >= cutoff
        ]
        if len(auto_reply_state["rtk_llm_call_timestamps"]) >= per_min:
            stats["llm_skipped"] += 1
            stats["tokens_saved_estimate"] += 80
            return False, "rate_limited", None

        # ── 4. Duplicate detection (exact + similarity) ──
        dup_window = auto_reply_settings.get("rtk_duplicate_window_sec", 60)
        sim_thresh = auto_reply_settings.get("rtk_dup_similarity_thresh", 0.85)
        # Trim old entries
        auto_reply_state["rtk_recent_comments"] = [
            (t, txt) for (t, txt) in auto_reply_state["rtk_recent_comments"]
            if now - t < dup_window
        ]
        # 4a. Exact match in cache
        cache = auto_reply_state["rtk_response_cache"]
        if comment_norm in cache and (now - cache[comment_norm]["ts"] < dup_window):
            stats["llm_cached"] += 1
            stats["tokens_saved_estimate"] += 80
            return False, "cache_exact", cache[comment_norm]["reply"]
        # 4b. Similarity match
        for prev_ts, prev_txt in auto_reply_state["rtk_recent_comments"]:
            if _rtk_jaccard(comment_norm, prev_txt) >= sim_thresh:
                # Look up cached reply for the similar text
                if prev_txt in cache:
                    stats["llm_cached"] += 1
                    stats["tokens_saved_estimate"] += 80
                    return False, "cache_similar", cache[prev_txt]["reply"]

        # All gates passed — allow LLM call
        return True, "ok", None


def _rtk_record_llm_call(username, comment, reply):
    """Record a successful LLM call into RTK caches (after _rtk_should_call_llm returned ok)."""
    with _RTK_LOCK:
        now = time.time()
        uname = (username or "").strip().lower()
        comment_norm = _rtk_normalize(comment)
        stats = auto_reply_state["rtk_stats"]

        # Update per-user cooldown
        if uname:
            auto_reply_state["rtk_per_user_last_llm"][uname] = now

        # Update token bucket
        auto_reply_state["rtk_llm_call_timestamps"].append(now)

        # Update recent comments
        auto_reply_state["rtk_recent_comments"].append((now, comment_norm))

        # Update response cache (with LRU eviction)
        cache = auto_reply_state["rtk_response_cache"]
        cache[comment_norm] = {"reply": reply, "ts": now}
        cache_max = auto_reply_settings.get("rtk_cache_max", 200)
        if len(cache) > cache_max:
            # Drop oldest entry
            oldest_key = min(cache.keys(), key=lambda k: cache[k]["ts"])
            cache.pop(oldest_key, None)

        stats["llm_calls"] += 1


def _rtk_pick_static_reply(comment):
    """Try to pick a context-aware static reply.
    Returns (reply_text, matched: bool). matched=False means no good static match.
    """
    words = (comment or "").lower().split()
    if not words:
        return None, False
    if any(w in words for w in ["kok", "kenapa", "gimana", "bagaimana"]):
        return random.choice([
            "Wah bagus nih pertanyaan",
            "Nah itu dia pertanyaan",
            "Bro kreatif juga",
        ]), True
    if any(w in words for w in ["wkwk", "haha", "lol", "wkwkwk", "xixi"]):
        return random.choice([
            "Komedian nih",
            "Lucu banget dah",
            "Wah garing nih",
        ]), True
    if any(w in words for w in ["keren", "mantap", "bagus", "good", "nice", "asik", "asikk"]):
        return random.choice([
            "ENGGAK ENGGAK",
            "BENER BANGET TU",
            "WKWK KAMU GOKIL",
        ]), True
    if any(w in words for w in ["mau", "dih", "dong", "donk", "pls", "tolong"]):
        return random.choice([
            "Gas bos",
            "SIAP BOS",
            "OKE OKE TUNGGU",
        ]), True
    if any(w in words for w in ["?", "apa", "siapa", "kapan", "dimana", "mana"]):
        return random.choice([
            "Pertanyaan mantap",
            "Hmm interesante",
            "Aku juga bingung",
        ]), True
    return None, False


def _rtk_build_prompt(comment, username, *, short=True):
    """Build the LLM prompt — compact (RTK) or verbose (original)."""
    if short and auto_reply_settings.get("rtk_short_prompts", True):
        # Compact: ~50% fewer input tokens
        return (
            f"Balas komentar TikTok ini singkat (max 5 kata, no emoji, sopan, lucu): "
            f"\"{comment}\""
        )
    return (
        f"Buatin reply lucu, RAMAH, dan SOPAN max 5 kata untuk komentar TikTok: \"{comment}\". "
        f"Jangan pakai emoji sama sekali, gak boleh vulgar atau gak sopan. "
        f"Contoh: 'Wah bagus nih pertanyaan' atau 'Komedian nih'. "
        f"Username: @{username}"
    )


def _remove_emoji(text):
    """Remove emoji characters from text for clean ASCII display + TTS."""
    if not text:
        return text
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002700-\U000027BF"  # dingbats
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended
        "\U00002600-\U000026FF"  # misc symbols
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text).strip()


def gen_auto_reply(username, comment):
    """Generate a funny auto-reply (max 5 words). Uses MiniMax LLM if configured.

    RTK (Rush Token Killer) layer:
      1. Try context-aware static reply (free, 0 tokens).
      2. If no match + LLM enabled: gate the call through RTK (cooldown, rate, dedup, cache).
      3. If RTK says no: pick from FUNNY_REPLIES (free fallback).
      4. If LLM fails or times out: same free fallback.
    """
    rtk_on = auto_reply_settings.get("rtk_enabled", True)

    # ── Static-first: pick a context-aware reply when we can ──
    if rtk_on and auto_reply_settings.get("rtk_static_first", True):
        static_reply, matched = _rtk_pick_static_reply(comment)
        if matched and static_reply:
            with _RTK_LOCK:
                auto_reply_state["rtk_stats"]["static_used"] += 1
            return _remove_emoji(static_reply)

    # ── LLM path (gated by RTK) ──
    if auto_reply_settings.get("llm_enabled") and auto_reply_settings.get("llm_api_key"):
        allow_llm, reason, cached_reply = _rtk_should_call_llm(username, comment)
        if cached_reply is not None:
            # Cache hit — return cached reply (0 tokens)
            log("RTK", "AUTO_REPLY", f"@{username} cache hit [{reason}]: {cached_reply!r}")
            return _remove_emoji(cached_reply)
        if not allow_llm:
            # Skipped (cooldown/rate/short) — fall through to static pool
            log("RTK", "AUTO_REPLY", f"@{username} LLM skipped [{reason}]: {comment!r}")
        else:
            # Reserve the slot BEFORE the call so a fast spammy stream
            # can't race through 5 LLM calls in a single tick
            with _RTK_LOCK:
                uname = (username or "").strip().lower()
                if uname:
                    auto_reply_state["rtk_per_user_last_llm"][uname] = time.time()
                auto_reply_state["rtk_llm_call_timestamps"].append(time.time())
                auto_reply_state["rtk_stats"]["llm_calls"] += 1
            prompt = _rtk_build_prompt(comment, username)
            reply = call_minimax(prompt, max_words=5)
            if reply:
                cleaned = _remove_emoji(reply)
                # Update cache with the new reply
                norm = _rtk_normalize(comment)
                with _RTK_LOCK:
                    auto_reply_state["rtk_response_cache"][norm] = {
                        "reply": cleaned, "ts": time.time()
                    }
                return cleaned
            # LLM failed — counters already updated above
            log("RTK", "AUTO_REPLY", f"@{username} LLM failed — falling back to static")
    else:
        # LLM disabled: count as a "saved" call so the metric reflects savings
        if rtk_on:
            with _RTK_LOCK:
                auto_reply_state["rtk_stats"]["llm_skipped"] += 1
                auto_reply_state["rtk_stats"]["tokens_saved_estimate"] += 80

    # Fallback to static pool
    words = (comment or "").lower().split()
    if any(w in words for w in ["kok", "kenapa", "gimana", "apa", "bagaimana"]):
        replies = [
            "Wah bagus nih pertanyaan",
            "Nah itu dia pertanyaan",
            "Bro kreatif juga",
        ]
    elif any(w in words for w in ["wkwk", "haha", "lol", "wkwkwk"]):
        replies = [
            "Komedian nih",
            "Lucu banget dah",
            "Wah garing nih",
        ]
    elif any(w in words for w in ["keren", "mantap", "bagus", "good", "nice"]):
        replies = [
            "ENGGAK ENGGAK",
            "BENER BANGET TU",
            "WKWK KAMU GOKIL",
        ]
    elif any(w in words for w in ["mau", "dih", "dong", "donk", "pls"]):
        replies = [
            "Gas bos",
            "SIAP BOS",
            "OKE OKE TUNGGU",
        ]
    else:
        replies = FUNNY_REPLIES

    reply = random.choice(replies)
    # Remove any stray emoji (static pool already clean but defensive)
    reply = _remove_emoji(reply)
    # Make sure max 5 words
    reply_words = reply.split()
    if len(reply_words) > 5:
        reply = " ".join(reply_words[:5])
    return reply


def gen_riddle():
    """Generate a riddle — uses MiniMax LLM if configured, else picks from static pool.

    RTK also applies here: rate-limit LLM riddle generation to once per 5 min
    (configurable). Other riddle cycles use the static pool — saves 99% of
    LLM riddle tokens while keeping variety.
    """
    rtk_on = auto_reply_settings.get("rtk_enabled", True)
    rtk_riddle_gap = 300  # 5 min
    if rtk_on:
        now = time.time()
        last = auto_reply_state.get("rtk_last_riddle_llm_ts", 0)
        if now - last < rtk_riddle_gap:
            # Throttled — use static pool only
            r = random.choice(RIDDLES)
            return {"q": r["q"], "a": r["a"], "ask_time": now, "fallback": True}

    if auto_reply_settings.get("llm_enabled") and auto_reply_settings.get("llm_api_key"):
        # RTK: compact riddle prompt
        if rtk_on and auto_reply_settings.get("rtk_short_prompts", True):
            prompt = (
                "Buat tebak-tebakan singkat (max 15 kata soal, 7 kata jawaban, no emoji, sopan, lucu). "
                'Format JSON: {"q": "...", "a": "..."}'
            )
            mt = 40 if auto_reply_settings.get("rtk_reduce_max_tokens") else 60
        else:
            prompt = (
                "Buatin tebak-tebakan lucu dalam Bahasa Indonesia yang FRIENDLY dan RAMAH. "
                "Semua jawaban harus SOPAN, gak boleh vulgar atau gak sopan. "
                "Pertanyaan max 10 kata, jawaban max 7 kata. "
                "Tidak pakai emoji sama sekali. Contoh: {\"q\": \"Benda apa yang kalau dipotong jadi panjang?\", \"a\": \"Waktu\"}"
            )
            mt = 60
        try:
            api_key = auto_reply_settings.get("llm_api_key", "").strip()
            base_url = auto_reply_settings.get("llm_base_url", "https://api.minimax.io/anthropic").strip().rstrip("/")
            model = auto_reply_settings.get("llm_model", "MiniMax-M2.7")
            url = f"{base_url}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": mt,
                "temperature": 0.8,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(raw.strip().strip("```json").strip("```").strip())
            q = _remove_emoji(parsed.get("q", "").strip())
            a = _remove_emoji(parsed.get("a", "").strip())
            q_words = q.split()
            if len(q_words) > 15:
                q = " ".join(q_words[:15])
            a_words = a.split()
            if len(a_words) > 7:
                a = " ".join(a_words[:7])
            if q and a:
                # Record LLM call for the token bucket
                with _RTK_LOCK:
                    auto_reply_state["rtk_last_riddle_llm_ts"] = time.time()
                    auto_reply_state["rtk_llm_call_timestamps"].append(time.time())
                    auto_reply_state["rtk_stats"]["llm_calls"] += 1
                return {"q": q, "a": a, "ask_time": time.time()}
        except Exception:
            pass
    # Fallback to static pool
    r = random.choice(RIDDLES)
    return {"q": r["q"], "a": r["a"], "ask_time": time.time(), "fallback": True}


def _auto_reply_loop():
    """Background loop: processes comment queue and fires riddles on idle."""
    global auto_reply_state

    while auto_reply_state["running"]:
        now = time.time()
        has_comment = len(auto_reply_state["comment_queue"]) > 0

        # Skip processing if riddle cycle is active (ASK→ANS→CTA)
        # or if currently displaying a reply (wait for display duration)
        if auto_reply_state["riddle_locked"] or auto_reply_state["reply_locked"]:
            # If reply is still displaying, check if we can release lock
            if auto_reply_state["reply_locked"]:
                elapsed = time.time() - auto_reply_state.get("reply_start_time", 0)
                display_sec = auto_reply_settings.get("reply_display_sec", 7)
                if elapsed >= display_sec:
                    auto_reply_state["reply_locked"] = False
                else:
                    time.sleep(0.5)
                    continue
            else:
                time.sleep(0.5)
                continue

        if has_comment:
            # Lock BEFORE rendering — no other display can start during text_to_ascii
            auto_reply_state["reply_locked"] = True
            auto_reply_state["reply_start_time"] = time.time()

            # Process ONE comment at a time (FIFO)
            username, comment = auto_reply_state["comment_queue"].pop(0)
            reply = gen_auto_reply(username, comment)

            # Render reply as ASCII art + emit (still under lock)
            ascii_reply = text_to_ascii(f"@{username}: {reply}", font=settings.get("font", "ansi_shadow"))
            payload = {
                "type": "auto_reply",
                "username": username,
                "original_comment": comment,
                "reply": reply,
                "ascii_content": ascii_reply,
                "timestamp": datetime.now().isoformat(),
                "display_sec": auto_reply_settings.get("reply_display_sec", 7),
            }
            state["active_display"] = {
                "content": ascii_reply,
                "type": "text",
                "original_text": f"@{username}: {reply}",
            }
            state["seq"]["auto_reply"] = state["seq"].get("auto_reply", 0) + 1
            payload["seq"] = state["seq"]["auto_reply"]
            socketio.emit("auto_reply_display", payload)
            speak_async(f"{username} {reply}")

            # Update last comment time
            auto_reply_state["last_comment_time"] = time.time()

            # Reset riddle timer when there's activity
            if auto_reply_state["riddle_timer"]:
                auto_reply_state["riddle_timer"].cancel()

            # Schedule next riddle after reply display duration
            idle_sec = auto_reply_settings.get("reply_display_sec", 7)
            auto_reply_state["riddle_timer"] = threading.Timer(
                idle_sec, _fire_riddle_ask
            )
            auto_reply_state["riddle_timer"].start()

            log("EVENT", "AUTO_REPLY", f"@{username}: {comment} → {reply}")

            # Keep lock held for entire display_sec — loop will release it after elapsed
            time.sleep(auto_reply_settings.get("reply_display_sec", 7))
            auto_reply_state["reply_locked"] = False
        else:
            # No comments — check if we should fire a riddle
            # (riddle timer handles this via _fire_riddle_ask)
            pass

        time.sleep(0.5)


def _fire_riddle_ask():
    """Timer callback: after idle_timeout, post riddle question."""
    global auto_reply_state
    if not auto_reply_settings["enabled"]:
        return

    # Always prioritize comment replies — skip riddle if queue has comments
    if auto_reply_state["comment_queue"]:
        log("EVENT", "AUTO_REPLY", "SKIP riddle — comments queued, processing first")
        return

    # Lock riddle cycle — queue comments until CTA done
    auto_reply_state["riddle_locked"] = True

    r = gen_riddle()
    auto_reply_state["current_riddle"] = r

    ascii_q = text_to_ascii(r["q"], font=settings.get("font", "ansi_shadow"))
    payload = {
        "type": "riddle_ask",
        "question": r["q"],
        "ascii_content": ascii_q,
        "timestamp": datetime.now().isoformat(),
        "fallback": r.get("fallback", False),
    }
    state["active_display"] = {
        "content": ascii_q,
        "type": "text",
        "original_text": r["q"],
    }
    state["seq"]["riddle"] = state["seq"].get("riddle", 0) + 1
    payload["seq"] = state["seq"]["riddle"]
    socketio.emit("riddle_display", payload)
    fallback_tag = " [static]" if r.get("fallback") else ""
    speak_async(r["q"])
    log("EVENT", "AUTO_REPLY", f"RIDDLE ASK:{fallback_tag} {r['q']}")

    # Schedule answer in riddle_interval_sec
    interval = auto_reply_settings["riddle_interval_sec"]
    auto_reply_state["riddle_timer"] = threading.Timer(
        interval, _fire_riddle_answer
    )
    auto_reply_state["riddle_timer"].start()


def _fire_riddle_answer():
    """Timer callback: post riddle answer after interval."""
    global auto_reply_state
    if not auto_reply_settings["enabled"]:
        return

    r = auto_reply_state.get("current_riddle")
    if not r:
        return

    ascii_a = text_to_ascii(f"Jawaban: {r['a']}", font=settings.get("font", "ansi_shadow"))
    state["seq"]["riddle"] = state["seq"].get("riddle", 0) + 1
    seq = state["seq"]["riddle"]
    payload = {
        "type": "riddle_answer",
        "question": r["q"],
        "answer": r["a"],
        "ascii_content": ascii_a,
        "timestamp": datetime.now().isoformat(),
        "fallback": r.get("fallback", False),
        "seq": seq,
    }
    state["active_display"] = {
        "content": ascii_a,
        "type": "text",
        "original_text": f"Jawaban: {r['a']}" + (" (static)" if r.get("fallback") else ""),
    }
    socketio.emit("riddle_display", payload)
    fallback_tag = " [static]" if r.get("fallback") else ""
    speak_async(f"Jawabannya adalah {r['a']}{fallback_tag}")
    log("EVENT", "AUTO_REPLY", f"RIDDLE ANS:{fallback_tag} {r['a']}")

    auto_reply_state["current_riddle"] = None

    # Schedule CTA after answer (wait riddle_interval_sec), then next riddle after CTA (wait idle_timeout_sec)
    interval = auto_reply_settings["riddle_interval_sec"]
    auto_reply_state["riddle_timer"] = threading.Timer(interval, _fire_cta)
    auto_reply_state["riddle_timer"].start()


def _fire_cta():
    """Show a CTA/sapaan after riddle answer."""
    global auto_reply_state
    if not auto_reply_settings["enabled"]:
        return

    # Lock reply processing during CTA display (5s) — not during idle wait
    auto_reply_state["reply_locked"] = True
    # Release reply_lock right before next riddle fires (end of idle period)
    threading.Timer(auto_reply_settings["idle_timeout_sec"], lambda: auto_reply_state.update({"reply_locked": False})).start()

    cta_text = random.choice(CTAS)
    ascii_cta = text_to_ascii(cta_text, font=settings.get("font", "ansi_shadow"))
    state["seq"]["cta"] = state["seq"].get("cta", 0) + 1
    payload = {
        "type": "cta",
        "content": cta_text,
        "ascii_content": ascii_cta,
        "timestamp": datetime.now().isoformat(),
        "tts_text": cta_text,  # TTS text for overlay to speak
        "seq": state["seq"]["cta"],
    }
    state["active_display"] = {
        "content": ascii_cta,
        "type": "text",
        "original_text": cta_text,
    }
    socketio.emit("cta_display", payload)
    speak_async(cta_text)
    log("EVENT", "AUTO_REPLY", f"CTA: {cta_text}")

    # After CTA display, schedule next riddle after idle_timeout_sec
    idle_sec = auto_reply_settings["idle_timeout_sec"]
    auto_reply_state["riddle_timer"] = threading.Timer(idle_sec, _fire_riddle_ask)
    auto_reply_state["riddle_timer"].start()

    # Unlock reply lock after CTA idle period — comments can now be processed again
    threading.Timer(idle_sec, lambda: auto_reply_state.update({"riddle_locked": False})).start()


def start_auto_reply_loop():
    """Start the background auto-reply processing loop."""
    global auto_reply_state
    if auto_reply_state["loop_thread"] and auto_reply_state["loop_thread"].is_alive():
        return
    auto_reply_state["running"] = True
    auto_reply_state["loop_thread"] = threading.Thread(target=_auto_reply_loop, daemon=True)
    auto_reply_state["loop_thread"].start()
    log("INFO", "AUTO_REPLY", "Background loop started")


def stop_auto_reply_loop():
    """Stop the background loop and cancel pending timers."""
    global auto_reply_state
    auto_reply_state["running"] = False
    if auto_reply_state["riddle_timer"]:
        auto_reply_state["riddle_timer"].cancel()
        auto_reply_state["riddle_timer"] = None
    log("INFO", "AUTO_REPLY", "Background loop stopped")


# ─── SETTINGS (continued) ───────────────────────────────────
settings = {
    "font": "ansi_shadow",
    "bigfont": "banner",
    "fgcolor": "#ffd700",
    "bgcolor": "#0a0a0f",
    "matrixcolor": "#00ff41",
    "matrix": False,
    "matrixspeed": 10,
    "duration": 0,
    "fontsize": 14,
    "padding": 20,
    "auto_font": False,
    "current_font_index": 0,
    "colormode": "gradient",
    "gradtop": "#FFD700",
    "gradmid": "#00E5FF",
    "gradbot": "#FF1493",
    # Gift settings
    "gift_message": DEFAULT_GIFT_MESSAGE,
    "gift_sound": DEFAULT_GIFT_SOUND,
    "gift_typing_speed": DEFAULT_GIFT_TYPING_SPEED,
    "gift_blink_duration": DEFAULT_GIFT_BLINK_DURATION,
    "gift_display_duration": DEFAULT_GIFT_DISPLAY_DURATION,
    "gift_enabled": True,
    # Screenshot settings
    "ss_mode": "auto",
    "ss_ratio": "square",
    "ss_flash": True,
    # Record settings
    "rec_duration": 5,
    "rec_mode": "auto",
}

FONT_POOL = [
    "ansi_shadow",  # 8 rows — full block chars, closest to Hermes-Agent (REFERENCE)
    "blocky",       # 8 rows — block character letters
    "starwars",     # 8 rows — dense sci-fi style
    "banner3",      # 8 rows — double-line block
    "banner4",      # 8 rows — dot-matrix style
    "banner",       # 9 rows — clean block letters
    "rounded",      # 8 rows — soft rounded block
]

@socketio.on("settings_update")
def on_settings_update(data):
    settings.update({k: v for k, v in data.items() if k in settings})

    # Kalau font berubah via scroll rotate, re-render konten aktif
    if "font" in data and state.get("active_display") and data.get("auto_font"):
        content_type = state["active_display"]["type"]
        original_text = state["active_display"].get("original_text", "")

        if original_text and content_type == "text":
            new_content = text_to_ascii(original_text, font=settings["font"])
            state["active_display"]["content"] = new_content
            socketio.emit("display_update", {
                "content": new_content,
                "type": content_type,
                "source": "manual",
                "font": settings["font"]
            })

    socketio.emit("settings_update", settings)
    log("INFO", "SETTINGS", f"Updated: {list(data.keys())}")

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify({"settings": settings})

@app.route("/api/settings/update", methods=["POST"])
def api_settings_update():
    data = request.get_json() or {}
    settings.update({k: v for k, v in data.items() if k in settings})
    socketio.emit("settings_update", settings)
    log("INFO", "SETTINGS", f"HTTP update: {list(data.keys())}")
    return {"status": "ok", "settings": settings}

@socketio.on("connect")
def on_connect():
    log("INFO", "SERVER", "Client connected")
    # Send current active display to newly connected client
    if state.get("active_display"):
        socketio.emit("display_update", state["active_display"], room=request.sid)

@socketio.on("disconnect")
def on_disconnect():
    log("INFO", "SERVER", "Client disconnected")

# ─── ROUTES ────────────────────────────────────────────────
@app.route("/")
def overlay_page():
    return render_template("overlay.html")

@app.route("/control")
def control_page():
    return render_template("control.html")

@app.route("/logs")
def logs_page():
    return render_template("logs.html")

@app.route("/test_ws")
def test_ws_page():
    return render_template("test_ws.html")

# ─── API: STATUS ───────────────────────────────────────────
@app.route("/api/status")
def api_status():
    # Merge RTK stats into state for live monitoring
    with _RTK_LOCK:
        rtk_view = {
            "stats": dict(auto_reply_state["rtk_stats"]),
            "calls_in_last_minute": len(auto_reply_state["rtk_llm_call_timestamps"]),
            "cache_size": len(auto_reply_state["rtk_response_cache"]),
        }
    out = dict(state)
    out["rtk"] = rtk_view
    return jsonify(out)

@app.route("/api/logs")
def api_logs():
    return jsonify(LOGS[-100:])

# ─── API: DISPLAY MANUAL ──────────────────────────────────
@app.route("/api/display/manual", methods=["POST"])
def api_display_manual():
    data = request.get_json() or {}
    content = data.get("content", "")
    content_type = data.get("type", "text")  # text|image|gif|video
    log("EVENT", "CONTROL", f"Manual display set: type={content_type} content={content[:50]}")

    # Simpan original_text SEBELUM conversion (untuk font rotation)
    original_text = ""
    if content_type == "text":
        original_text = content  # teks asli, belum di-ASCII-kan
    elif content_type == "bigtext":
        original_text = content.upper()  # teks asli uppercase
    # block/half/image/gif/video → original_text = "" (tidak bisa di-re-render)

    # Convert text to ASCII art
    if content_type == "text" and content:
        content = text_to_ascii(content, font=settings["font"])
    elif content_type == "block" and content:
        content = block_render(content)
    elif content_type == "half" and content:
        content = block_half(content)
    elif content_type == "bigtext" and content:
        content = text_to_ascii(content.upper(), font=settings["bigfont"])
    elif content_type in ("image", "gif", "video") and content:
        pass  # pass through base64/URL as-is

    # Simpan konten aktif untuk re-render saat font rotate
    state["active_display"] = {
        "content": content,
        "type": content_type,
        "original_text": original_text,
    }

    state["seq"]["manual"] = state["seq"].get("manual", 0) + 1
    socketio.emit("display_update", {
        "content": content,
        "type": content_type,
        "source": "manual",
        "seq": state["seq"]["manual"],
    })

    # TTS: speak each word as it appears on display
    if original_text:
        speak_async(original_text)

    # Auto screenshot if enabled
    if settings.get("ss_mode") == "auto" and content:
        import time; time.sleep(0.3)
        socketio.emit("auto_ss", {"type": content_type, "content_type": content_type})

    return jsonify({"ok": True})

# ─── API: TIKTOK SETUP ─────────────────────────────────────
@app.route("/api/tiktok/connect", methods=["POST"])
def api_tiktok_connect():
    room_id = request.json.get("room_id", "")
    web_proxy = request.json.get("web_proxy", None) or None
    ws_proxy = request.json.get("ws_proxy", None) or None
    log("EVENT", "TIKTOK", f"Connect requested to room: {room_id} | proxy: {web_proxy or 'none'}")
    state["tiktok_status"] = "CONNECTING"
    socketio.emit("status_update", {"tiktok_status": "CONNECTING"})
    threading.Thread(target=connect_tiktok, args=(room_id, web_proxy, ws_proxy), daemon=True).start()
    return jsonify({"ok": True, "room_id": room_id})

@app.route("/api/tiktok/disconnect", methods=["POST"])
def api_tiktok_disconnect():
    state["tiktok_status"] = "DISCONNECTED"
    socketio.emit("status_update", {"tiktok_status": "DISCONNECTED"})
    log("INFO", "TIKTOK", "Disconnected")
    return jsonify({"ok": True})

@app.route("/api/tiktok/simulate", methods=["POST"])
def api_tiktok_simulate():
    """For testing — simulate a single comment"""
    username = request.json.get("username", "TestUser")
    comment = request.json.get("comment", "Halo dari test!")
    handle_tiktok_comment(username, comment)
    return jsonify({"ok": True})

@app.route("/api/tiktok/simulate_batch", methods=["POST"])
def api_tiktok_simulate_batch():
    """Flood test — simulate multiple comments with varied accounts"""

    ACCOUNTS = [
        "NeonDev", "MatrixLover", "CyberNerd", "AI_Fan", "CodeMaster",
        "TechGeek", "ByteRunner", "PixelWave", "DataStream", "VortexAI",
        "GlitchMaster", "RetroWave", "SynthByte", "NeuralNex", "CryptoPunk",
        "DarkMatrix", "LightSpeed", "QuantumFox", "TurboC0de", "SkyWalker"
    ]

    COMMENTS = [
        "keren banget!", "subs first!", "how made this??", "gila ini tools",
        "mau dong!", "bagus banget 🔥", "cara install nya gimana?",
        "recommended!", "nice666", "ini apa ya?",
        "join server kita!", "cek bio untuk free tools",
        "wow amazing! 🎉", "keep streaming!", "love this stream",
        "gak ngerti tapi keren", "tutorial dong", "linknya mana?",
        "masuk sini bro", "DM dong!", "subs ya!"
    ]

    count = request.json.get("count", 5)
    delay = request.json.get("delay", 1.0)

    results = []
    for i in range(count):
        user = random.choice(ACCOUNTS)
        text = random.choice(COMMENTS)
        handle_tiktok_comment(user, text)
        results.append(f"@{user}: {text}")
        if delay > 0 and i < count - 1:
            time.sleep(delay)

    return jsonify({"ok": True, "sent": results})

# ─── API: AUTO REPLY (AI Chat) ───────────────────────────────
@app.route("/api/auto_reply/enable", methods=["POST"])
def api_auto_reply_enable():
    auto_reply_settings["enabled"] = True
    start_auto_reply_loop()
    # Fire first riddle immediately (don't wait idle_timeout)
    if not auto_reply_state.get("current_riddle"):
        # Cancel any pending timer and fire now
        if auto_reply_state.get("riddle_timer"):
            auto_reply_state["riddle_timer"].cancel()
        _fire_riddle_ask()
    log("INFO", "AUTO_REPLY", "Enabled")
    return jsonify({"ok": True, "enabled": True})

@app.route("/api/auto_reply/disable", methods=["POST"])
def api_auto_reply_disable():
    auto_reply_settings["enabled"] = False
    stop_auto_reply_loop()
    log("INFO", "AUTO_REPLY", "Disabled")
    return jsonify({"ok": True, "enabled": False})

@app.route("/api/auto_reply/status", methods=["GET"])
def api_auto_reply_status():
    return jsonify({
        "enabled": auto_reply_settings["enabled"],
        "settings": auto_reply_settings,
        "queue_size": len(auto_reply_state["comment_queue"]),
        "current_riddle": auto_reply_state.get("current_riddle"),
    })

@app.route("/api/auto_reply/test_comment", methods=["POST"])
def api_auto_reply_test_comment():
    """Simulate a test comment into the auto-reply queue."""
    username = request.json.get("username", "TestUser")
    comment = request.json.get("comment", "Test comment lucu!")
    handle_tiktok_comment(username, comment)
    return jsonify({"ok": True, "queued": f"@{username}: {comment}"})

@app.route("/api/auto_reply/test_riddle", methods=["POST"])
def api_auto_reply_test_riddle():
    """Fire a test riddle immediately (question + answer back-to-back for demo)."""
    r = gen_riddle()
    ascii_q = text_to_ascii(r["q"], font=settings.get("font", "ansi_shadow"))
    ascii_a = text_to_ascii(f"Jawaban: {r['a']}", font=settings.get("font", "ansi_shadow"))
    state["seq"]["riddle"] = state["seq"].get("riddle", 0) + 1
    q_seq = state["seq"]["riddle"]
    state["seq"]["riddle"] = state["seq"].get("riddle", 0) + 1
    a_seq = state["seq"]["riddle"]
    socketio.emit("riddle_display", {
        "type": "riddle_ask",
        "question": r["q"],
        "ascii_content": ascii_q,
        "timestamp": datetime.now().isoformat(),
        "fallback": r.get("fallback", False),
        "seq": q_seq,
    })
    # Fire answer after 5 seconds
    threading.Timer(5.0, lambda seq=a_seq, r=r, ascii_a=ascii_a: socketio.emit("riddle_display", {
        "type": "riddle_answer",
        "question": r["q"],
        "answer": r["a"],
        "ascii_content": ascii_a,
        "timestamp": datetime.now().isoformat(),
        "fallback": r.get("fallback", False),
        "seq": seq,
    })).start()
    return jsonify({"ok": True, "riddle": r})

@app.route("/api/auto_reply/riddles", methods=["GET"])
def api_auto_reply_riddles():
    """Return all riddles in the pool."""
    return jsonify({"riddles": RIDDLES})


def handle_tiktok_comment(username, comment):
    """Handler for TikTok comments — relay to overlay AND queue for auto-reply."""
    state["event_count"] += 1
    log("EVENT", "TIKTOK", f"Comment: @{username}: {comment}")
    socketio.emit("tiktok_comment", {
        "username": username,
        "comment": comment,
        "timestamp": datetime.now().isoformat(),
        "event_num": state["event_count"]
    })
    # Queue for auto-reply processing
    if auto_reply_settings["enabled"]:
        auto_reply_state["comment_queue"].append((username, comment))

# ─── TIKTOK CONNECTOR ─────────────────────────────────────
tiktok_conn = None

def connect_tiktok(room_id, web_proxy=None, ws_proxy=None):
    """Start TikTok live listener using TikTokLive library"""
    global tiktok_conn
    from tiktok.connector import TikTokConnector

    def on_comment(username, comment):
        state["event_count"] += 1
        log("EVENT", "TIKTOK", f"Comment: @{username}: {comment}")
        socketio.emit("tiktok_comment", {
            "username": username,
            "comment": comment,
            "timestamp": datetime.now().isoformat(),
            "event_num": state["event_count"]
        })

    def on_gift(username, gift_name):
        log("EVENT", "TIKTOK", f"Gift: @{username} sent {gift_name}")
        # Trigger gift animation if enabled
        if settings.get("gift_enabled", True):
            # Normalize gift name to key
            gift_key = gift_name.lower().replace(" ", "_").replace("-", "_")
            if gift_key not in GIFT_ARTS:
                # Try partial match
                for k in GIFT_ARTS:
                    if k in gift_key or gift_key in k:
                        gift_key = k
                        break
                else:
                    gift_key = "star"  # fallback
            gift = GIFT_ARTS[gift_key]
            gift_msg_lines = GIFT_MESSAGES.get(gift_key, GIFT_MESSAGES["star"])
            # Substitute placeholders in each line
            message_lines = []
            for line in gift_msg_lines:
                message_lines.append(line.replace("@Kiozhu", f"@{username}"))
            socketio.emit("gift_display", {
                "username": username,
                "username_ascii": pyfiglet.Figlet(font="ansi_shadow", width=200).renderText(username),
                "gift_type": gift_key,
                "gift_art": normalize_gift_art(gift["art"]),
                "gift_emoji": gift["emoji"],
                "gift_name": gift["title"],
                "gift_message_lines": message_lines,
                # NOTE: all timing hardcoded in overlay.html — 10s total
                "sound": settings["gift_sound"] if settings["gift_enabled"] else "off",
            })
        else:
            socketio.emit("tiktok_gift", {"username": username, "gift": gift_name})

    def on_connect(uid, room_id):
        log("INFO", "TIKTOK", f"CONNECTED to @{uid} (room_id={room_id})")
        state["tiktok_unique_id"] = uid
        state["tiktok_room_id"] = room_id
        socketio.emit("status_update", {
            "tiktok_status": "CONNECTED",
            "unique_id": uid,
            "room_id": room_id,
        })

    def on_disconnect():
        log("INFO", "TIKTOK", "Disconnected from live")
        state["tiktok_status"] = "DISCONNECTED"
        socketio.emit("status_update", {"tiktok_status": "DISCONNECTED"})

    def on_status(status):
        state["tiktok_status"] = status
        socketio.emit("status_update", {"tiktok_status": status})
        log("EVENT", "TIKTOK", f"Status: {status}")

    def on_error(msg):
        state["tiktok_status"] = "ERROR"
        socketio.emit("status_update", {"tiktok_status": "ERROR", "tiktok_error": msg})
        log("ERROR", "TIKTOK", f"Connection failed: {msg}")

    def on_retry(attempt, last_error):
        state["tiktok_status"] = f"RETRY ({attempt})"
        socketio.emit("status_update", {"tiktok_status": f"RETRY ({attempt})", "tiktok_error": last_error})
        log("INFO", "TIKTOK", f"Retry {attempt} — {last_error}")

    tiktok_conn = TikTokConnector(
        room_id,
        on_comment_callback=on_comment,
        on_gift_callback=on_gift,
        on_connect_callback=on_connect,
        on_error_callback=on_error,
        on_status_callback=on_status,
        on_disconnect_callback=on_disconnect,
        on_retry_callback=on_retry,
        web_proxy=web_proxy,
        ws_proxy=ws_proxy,
    )
    tiktok_conn.connect()

# ─── GIFT ART NORMALIZER ────────────────────────────────────
# Gift arts were stored as single-line with color-tags marking line breaks.
# This splits them into proper multi-line format for display.
def normalize_gift_art(raw):
    """Convert per-char coloring into line-by-line format.

    Each line in `raw` may have a different [bold #COLOR] / [#COLOR] tag.
    We carry the last-seen opening tag forward to each non-empty content line,
    and close with [/] after every content snippet.
    """
    global _tag_pattern, _content_pattern
    if "_tag_pattern" not in globals():
        _tag_pattern = re.compile(r'\[(?:bold )?#([0-9A-Fa-f]{6})\]')
        _content_pattern = re.compile(r'\[/?\]')

    lines_out = []
    for line in raw.split('\n'):
        line_content = line.rstrip('\n')
        if not line_content:
            continue  # skip blank lines

        # Extract any opening tag from this line
        tag_match = _tag_pattern.search(line_content)
        if tag_match:
            # Determine tag type (bold or plain)
            full_tag_start = _tag_pattern.search(line_content).group(0)
            if full_tag_start.startswith('[bold'):
                current_tag = full_tag_start  # e.g. '[bold #FFD700]'
            else:
                current_tag = full_tag_start  # e.g. '[#FFD700]'

        # Remove any lingering markup tokens from the content
        clean = _content_pattern.sub('', line_content)

        # Strip the color tag prefix to get pure art content
        clean = _tag_pattern.sub('', clean)

        if current_tag:
            lines_out.append(current_tag + clean + '[/]')
        else:
            lines_out.append(clean)

    return '\n'.join(lines_out)


# ─── GIFT DISPLAY ───────────────────────────────────────────
@app.route("/api/gift/test", methods=["POST"])
def api_gift_test():
    """Test gift animation with a sample gift"""
    data = request.get_json() or {}
    gift_type = data.get("gift_type", "rose")
    username = data.get("username", "TestUser")

    if gift_type not in GIFT_ARTS:
        return jsonify({"error": f"Unknown gift type: {gift_type}. Available: {list(GIFT_ARTS.keys())}"}), 400

    gift = GIFT_ARTS[gift_type]
    gift_msg_lines = GIFT_MESSAGES.get(gift_type, GIFT_MESSAGES["star"])
    message_lines = [line.replace("@Kiozhu", f"@{username}") for line in gift_msg_lines]

    payload = {
        "username": username,
        "username_ascii": pyfiglet.Figlet(font="ansi_shadow", width=200).renderText(username),
        "gift_type": gift_type,
        "gift_art": normalize_gift_art(gift["art"]),
        "gift_emoji": gift["emoji"],
        "gift_name": gift["title"],
        "gift_message_lines": message_lines,
        # NOTE: all timing is now hardcoded in overlay.html:
        # Phase 1 typing = 4000ms, Phase 2 dramatic = 6000ms, total = 10000ms
        "sound": settings["gift_sound"] if settings["gift_enabled"] else "off",
    }

    socketio.emit("gift_display", payload)
    log("EVENT", "GIFT", f"Test gift sent: {gift_type} for @{username} | {len(message_lines)} lines | 10s total")

    # Auto screenshot if enabled
    if settings.get("ss_mode") == "auto":
        import time; time.sleep(0.5)
        socketio.emit("auto_ss", {"type": "test_gift", "gift_type": gift_type})

    # Auto record if enabled
    if settings.get("rec_mode") == "auto":
        import time; time.sleep(0.3)
        socketio.emit("auto_rec", {"type": "test_gift", "gift_type": gift_type})

    import time; time.sleep(0.3)  # give socketIO time to deliver before HTTP returns
    return jsonify({"ok": True, "payload": payload})


@app.route("/api/gift/trigger", methods=["POST"])
def api_gift_trigger():
    """Trigger a real gift event (called by TikTok handler)"""
    data = request.get_json() or {}
    gift_type = data.get("gift_type", "rose")
    username = data.get("username", "Guest")

    if not settings.get("gift_enabled", True):
        return jsonify({"ok": True, "skipped": True, "reason": "gift_enabled=false"})

    if gift_type not in GIFT_ARTS:
        gift_type = "star"  # fallback

    gift = GIFT_ARTS[gift_type]
    gift_msg_lines = GIFT_MESSAGES.get(gift_type, GIFT_MESSAGES["star"])
    message_lines = [line.replace("@Kiozhu", f"@{username}") for line in gift_msg_lines]

    payload = {
        "username": username,
        "username_ascii": pyfiglet.Figlet(font="ansi_shadow", width=200).renderText(username),
        "gift_type": gift_type,
        "gift_art": normalize_gift_art(gift["art"]),
        "gift_emoji": gift["emoji"],
        "gift_name": gift["title"],
        "gift_message_lines": message_lines,
        "typing_speed": settings["gift_typing_speed"],
        "blink_duration": settings["gift_blink_duration"],
        "display_duration": settings["gift_display_duration"],
        "sound": settings["gift_sound"] if settings["gift_enabled"] else "off",
    }

    socketio.emit("gift_display", payload)
    log("EVENT", "GIFT", f"🎁 Gift triggered: {gift_type} from @{username}")

    # Auto screenshot if enabled
    if settings.get("ss_mode") == "auto":
        import time; time.sleep(0.5)  # wait for animation to start
        socketio.emit("auto_ss", {"type": "gift", "gift_type": gift_type})

    # Auto record if enabled
    if settings.get("rec_mode") == "auto":
        import time; time.sleep(0.3)
        socketio.emit("auto_rec", {"type": "gift", "gift_type": gift_type})

    return jsonify({"ok": True})


@app.route("/api/gift/list", methods=["GET"])
def api_gift_list():
    """List available gift types"""
    return jsonify({
        "gifts": {
            key: {"emoji": v["emoji"], "title": v["title"]}
            for key, v in GIFT_ARTS.items()
        },
        "settings": {
            "gift_enabled": settings.get("gift_enabled", True),
            "gift_sound": settings.get("gift_sound", "on"),
            "gift_message": settings.get("gift_message", DEFAULT_GIFT_MESSAGE),
        }
    })

# ─── CLEAR DISPLAY ─────────────────────────────────────────
@app.route("/api/display/clear", methods=["POST"])
def api_clear():
    log("EVENT", "CONTROL", "Display cleared")
    state["seq"]["manual"] = state["seq"].get("manual", 0) + 1
    socketio.emit("display_update", {"content": None, "type": "none", "source": "clear", "seq": state["seq"]["manual"]})
    return jsonify({"ok": True})

# ─── TELEGRAM BOT ───────────────────────────────────────────
telegram_bot = None

def stop_telegram():
    """Stop current Telegram bot if running"""
    global telegram_bot
    if telegram_bot:
        telegram_bot.stop()
        telegram_bot = None

def init_telegram(token=None, admin_chat_id=None, enabled=None):
    """Initialize Telegram bot — reads from .env or accepts runtime overrides"""
    global telegram_bot
    # Stop existing bot first
    stop_telegram()

    from telegram_bot.bot import start_telegram_bot
    # Runtime overrides take precedence over .env
    bot_token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = admin_chat_id if admin_chat_id is not None else os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    telegram_enabled = enabled if enabled is not None else os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

    if not telegram_enabled:
        log("INFO", "TELEGRAM", "Telegram trigger disabled")
        return None
    if not bot_token or bot_token == "***":
        log("INFO", "TELEGRAM", "No bot token configured")
        return None

    # Accept int or string; validate numeric
    admin_chat_id_int = None
    if admin_id is not None:
        if isinstance(admin_id, int):
            admin_chat_id_int = admin_id
        elif isinstance(admin_id, str) and admin_id.isdigit():
            admin_chat_id_int = int(admin_id)
    bot = start_telegram_bot(bot_token, admin_chat_id_int)
    if bot:
        log("INFO", "TELEGRAM", "Telegram bot activated")
    return bot

@app.route("/api/telegram/config", methods=["POST"])
def api_telegram_config():
    """Update Telegram config at runtime — token + enabled + admin_chat_id"""
    global telegram_bot
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    admin_chat_id = data.get("admin_chat_id", "").strip()
    enabled = data.get("enabled", False)
    chat_id_str = str(admin_chat_id) if admin_chat_id else ""

    # Persist to .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_lines = f.readlines()

    updated = False
    new_lines = []
    keys_to_set = {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_ADMIN_CHAT_ID": chat_id_str,
        "TELEGRAM_ENABLED": "true" if enabled else "false",
    }
    keys_found = set()
    for line in env_lines:
        stripped = line.strip()
        matched = False
        for key in keys_to_set:
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={keys_to_set[key]}\n")
                keys_found.add(key)
                matched = True
                updated = True
                break
        if not matched:
            new_lines.append(line)
    for key, val in keys_to_set.items():
        if key not in keys_found:
            new_lines.append(f"{key}={val}\n")
            updated = True
    if updated:
        with open(env_path, "w") as f:
            f.writelines(new_lines)

    # Reload from .env
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["TELEGRAM_ADMIN_CHAT_ID"] = chat_id_str
    os.environ["TELEGRAM_ENABLED"] = "true" if enabled else "false"

    # Restart bot with new config
    init_telegram(token=token, admin_chat_id=chat_id_str, enabled=enabled)
    return jsonify({"ok": True, "enabled": enabled, "token_set": bool(token)})

@app.route("/api/telegram/status")
def api_telegram_status():
    """Return Telegram bot status"""
    global telegram_bot
    return jsonify({
        "enabled": telegram_bot is not None,
        "token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
    })

# ─── API: MiniMax LLM CONFIG ─────────────────────────────────
@app.route("/api/llm/config", methods=["POST"])
def api_llm_config():
    """Update MiniMax LLM config at runtime — key + base_url + model + enabled"""
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    base_url = data.get("base_url", "https://api.minimax.io/anthropic").strip().rstrip("/")
    model = data.get("model", "MiniMax-M2.7").strip()
    enabled = bool(data.get("enabled", False))

    # Update runtime settings
    auto_reply_settings["llm_api_key"] = api_key
    auto_reply_settings["llm_base_url"] = base_url
    auto_reply_settings["llm_model"] = model
    auto_reply_settings["llm_enabled"] = enabled

    # Persist to .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_lines = f.readlines()

    keys_to_set = {
        "MINIMAX_API_KEY": api_key,
        "MINIMAX_BASE_URL": base_url,
        "MINIMAX_MODEL": model,
        "MINIMAX_ENABLED": "true" if enabled else "false",
    }
    keys_found = set()
    new_lines = []
    for line in env_lines:
        stripped = line.strip()
        matched = False
        for key in keys_to_set:
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={keys_to_set[key]}\n")
                keys_found.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for key, val in keys_to_set.items():
        if key not in keys_found:
            new_lines.append(f"{key}={val}\n")
    with open(env_path, "w") as f:
        f.writelines(new_lines)

    # Reload env
    for k, v in keys_to_set.items():
        os.environ[k] = v

    return jsonify({
        "ok": True,
        "llm_enabled": enabled,
        "llm_api_key_set": bool(api_key),
        "llm_model": model,
        "llm_base_url": base_url,
    })


# ─── API: RTK (RUSH TOKEN KILLER) ─────────────────────────────
@app.route("/api/rtk/stats", methods=["GET"])
def api_rtk_stats():
    """Live RTK metrics — token savings, cache hits, rate-limit hits."""
    with _RTK_LOCK:
        # compute "calls saved" vs hypothetical baseline
        baseline = (
            auto_reply_state["rtk_stats"]["llm_calls"]
            + auto_reply_state["rtk_stats"]["llm_skipped"]
            + auto_reply_state["rtk_stats"]["llm_cached"]
        )
        actual = auto_reply_state["rtk_stats"]["llm_calls"]
        saved = baseline - actual
        pct = round((saved / baseline) * 100, 1) if baseline else 0.0
        return jsonify({
            "ok": True,
            "stats": dict(auto_reply_state["rtk_stats"]),
            "calls_in_last_minute": len(auto_reply_state["rtk_llm_call_timestamps"]),
            "cache_size": len(auto_reply_state["rtk_response_cache"]),
            "recent_users_throttled": len(auto_reply_state["rtk_per_user_last_llm"]),
            "summary": {
                "llm_calls_made": actual,
                "llm_calls_baseline": baseline,
                "llm_calls_saved": saved,
                "savings_pct": pct,
            },
            "config": {
                "rtk_enabled": auto_reply_settings.get("rtk_enabled"),
                "per_user_cooldown_sec": auto_reply_settings.get("rtk_per_user_cooldown_sec"),
                "global_rate_per_min": auto_reply_settings.get("rtk_global_rate_per_min"),
                "duplicate_window_sec": auto_reply_settings.get("rtk_duplicate_window_sec"),
                "min_comment_len": auto_reply_settings.get("rtk_min_comment_len"),
                "static_first": auto_reply_settings.get("rtk_static_first"),
                "short_prompts": auto_reply_settings.get("rtk_short_prompts"),
                "reduce_max_tokens": auto_reply_settings.get("rtk_reduce_max_tokens"),
            },
        })


@app.route("/api/rtk/reset", methods=["POST"])
def api_rtk_reset():
    """Reset RTK caches and stats — useful for testing or after config change."""
    with _RTK_LOCK:
        auto_reply_state["rtk_per_user_last_llm"].clear()
        auto_reply_state["rtk_recent_comments"].clear()
        auto_reply_state["rtk_llm_call_timestamps"].clear()
        auto_reply_state["rtk_response_cache"].clear()
        auto_reply_state["rtk_last_riddle_llm_ts"] = 0
        for k in auto_reply_state["rtk_stats"]:
            auto_reply_state["rtk_stats"][k] = 0
    return jsonify({"ok": True})


@app.route("/api/rtk/config", methods=["POST"])
def api_rtk_config():
    """Update RTK settings at runtime."""
    data = request.get_json() or {}
    int_keys = (
        "rtk_per_user_cooldown_sec", "rtk_global_rate_per_min",
        "rtk_duplicate_window_sec", "rtk_cache_max", "rtk_min_comment_len",
    )
    bool_keys = (
        "rtk_enabled", "rtk_static_first", "rtk_short_prompts", "rtk_reduce_max_tokens",
    )
    float_keys = ("rtk_dup_similarity_thresh",)
    for k in int_keys:
        if k in data:
            try:
                auto_reply_settings[k] = int(data[k])
            except (TypeError, ValueError):
                pass
    for k in bool_keys:
        if k in data:
            auto_reply_settings[k] = bool(data[k])
    for k in float_keys:
        if k in data:
            try:
                v = float(data[k])
                auto_reply_settings[k] = max(0.0, min(1.0, v))
            except (TypeError, ValueError):
                pass
    return jsonify({"ok": True, "config": {k: auto_reply_settings.get(k) for k in (*int_keys, *bool_keys, *float_keys)}})


@app.route("/api/llm/status")
def api_llm_status():
    """Return MiniMax LLM status"""
    return jsonify({
        "llm_enabled": auto_reply_settings.get("llm_enabled", False),
        "llm_api_key_set": bool(auto_reply_settings.get("llm_api_key", "").strip()),
        "llm_model": auto_reply_settings.get("llm_model", "MiniMax-M2.7"),
        "llm_base_url": auto_reply_settings.get("llm_base_url", "https://api.minimax.io/anthropic"),
    })

# ─── SERVER STATUS ─────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "uptime": time.time()})

@app.route("/api/hermes/art")
def api_hermes_art():
    """Return Hermes banner art"""
    style = request.args.get("style", "full")
    return jsonify({"art": get_hermes_art(style)})

# Font width factors relative to standard (empirical)
# Wider chars = smaller font size needed to fit same space
FONT_WIDTH_FACTORS = {
    # ── Target: semua font nge-render 'HERMES' di lebar yang sama ──
    # Reference: ansi_shadow @ fontsize=14 (51 chars wide)
    # Formula: factor = BASE(14) / target_size
    
    "banner":        0.93,   # 47 chars              → target 15px
    "rounded":      0.93,   # 49 chars              → target 15px
    "blocky":        1.08,   # 56 chars              → target 13px
    "banner3":       1.08,   # 56 chars              → target 13px
    "banner4":       1.08,   # 57 chars              → target 13px
    "starwars":      1.27,   # 65 chars              → target 11px (paling small)
    "ansi_shadow":   1.00,   # 51 chars reference    → target 14px
}

# Base fontsize (user-configured, for "standard" font)
BASE_FONTSIZE = 14

def get_fontsize(font_name):
    """Get adjusted font size to maintain visual consistency across fonts"""
    factor = FONT_WIDTH_FACTORS.get(font_name, 1.0)
    return round(BASE_FONTSIZE / factor)


@app.route("/api/font/rotate", methods=["POST"])
def api_font_rotate():
    """Rotate to next font and re-render active display"""
    fonts = [
        "ansi_shadow", "blocky", "starwars",
        "banner3", "banner4", "banner", "rounded"
    ]
    current = settings.get("font", "ansi_shadow")
    try:
        idx = fonts.index(current)
    except ValueError:
        idx = 0
    next_font = fonts[(idx + 1) % len(fonts)]
    settings["font"] = next_font

    # Adjust fontsize for visual consistency
    settings["fontsize"] = get_fontsize(next_font)

    # Re-render active display if exists
    if state.get("active_display") and state["active_display"].get("original_text"):
        original = state["active_display"]["original_text"]
        content = text_to_ascii(original, font=next_font)
        state["active_display"]["content"] = content
        state["active_display"]["font"] = next_font
        state["seq"]["manual"] = state["seq"].get("manual", 0) + 1
        socketio.emit("display_update", {
            "content": content,
            "type": state["active_display"]["type"],
            "source": "font_rotate",
            "font": next_font,
            "fontsize": settings["fontsize"],
            "seq": state["seq"]["manual"],
        })

    socketio.emit("settings_update", settings)
    log("INFO", "FONT", f"Rotated to: {next_font} (fontsize={settings['fontsize']})")
    return jsonify({"font": next_font, "settings": settings})

# ─── STARTUP ───────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    host = os.getenv("HOST", "0.0.0.0")
    log("INFO", "SERVER", f"ASCII Overlay starting on {host}:{port}")
    state["server_status"] = "RUNNING"
    socketio.emit("status_update", {"server_status": "RUNNING"})

    # Start Telegram bot
    init_telegram()

    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)