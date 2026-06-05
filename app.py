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
    "overlay_content": None,
    "manual_content": None,
    "event_count": 0,
    "live_id": None,
    "active_display": None,  # {content, type} - konten yang sedang aktif display
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
    "idle_timeout_sec": 5,     # seconds to wait after last comment before starting riddle cycle
    "riddle_interval_sec": 5,  # seconds between riddle → answer
    "max_words": 5,            # max words per reply
    "reply_style": "funny",    # "funny" | "sarcastic" | "random"
}

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
}

# Funny reply templates (max 5 words each)
FUNNY_REPLIES = [
    "Wkwk kreatif juga 😂",
    "Hah serius nih? 😏",
    "Otak di luar ya? 🤯",
    "Kok bisa gitu sih 🤯",
    "Level tinggi banget 🎮",
    "Yakin? Check lagi deh 👀",
    "Kagak salah kan? 😜",
    "Keren abis gak sih 🔥",
    "Auto nangis aku 🥲",
    "WAIT APA?? 🤯",
    "KAMU NIH PASTI? 👀",
    "Wah ada yang salah 🤔",
    "Lebay banget dah 😂",
    "Gas terus bang 👊",
    "KALAU BENER INI GILA 😂",
    "Makasih participate 🫡",
    "PING PONG 🍜",
    "Gak paham tapi oke 🤝",
    "Bro level berapa 🫡",
    "Mantap jiwa bang 👊🔥",
    "KODE RED 🤖",
    "NOTED 📝",
    "AUTO LIKE ✅",
    "SALAH KAPRAH 😎",
    "WAW KEREN BANGET ☄️",
    "SAD BOYS 💔",
    "GAMERS ONLY 🎮",
    "NO COMMENTS 📝❌",
    "WAIT WAIT WAIT 🤯",
    "FIX TIE 🧍",
    "LUAR BIASA GANS 😍",
    "MATA GUA SISA SATU 👁️",
    "BENER BANGET ITU 🤝",
    "YANG MANA? 🤯",
    "PANIK GANS 😭😂",
    "FIX INI YANG BENER ✅",
]


def gen_auto_reply(username, comment):
    """Generate a funny auto-reply (max 5 words)."""
    words = comment.lower().split()
    # Context-aware responses
    if any(w in words for w in ["kok", "kenapa", "gimana", "apa", "bagaimana"]):
        replies = [
            "Yaelah gitu aja tahu 🤔",
            "Nah itu dia pertanyaan 🤔",
            "Bro pertanyaan itu susah 👀",
        ]
    elif any(w in words for w in ["wkwk", "haha", "lol", "wkwkwk"]):
        replies = [
            "Ketawa apaan sih 😂",
            "Ngakak parah 😭",
            "LUAR BIASA INI 😂",
        ]
    elif any(w in words for w in ["keren", "mantap", "bagus", "good", "nice"]):
        replies = [
            "ENGGAK ENGGAK 🥲",
            "BENER BANGET TU 🙌",
            "WKWK KAMU GOKIL 🤯",
        ]
    elif any(w in words for w in ["mau", "dih", "dong", "donk", "pls"]):
        replies = [
            "Gak semurah itu bang 😂",
            "SIAP BOS 🫡",
            "OKE OKE TUNGGU 📝",
        ]
    else:
        replies = FUNNY_REPLIES

    reply = random.choice(replies)
    # Make sure max 5 words
    reply_words = reply.split()
    if len(reply_words) > 5:
        reply = " ".join(reply_words[:5])
    return reply


def gen_riddle():
    """Pick a random riddle from pool."""
    r = random.choice(RIDDLES)
    return {"q": r["q"], "a": r["a"], "ask_time": time.time()}


def _auto_reply_loop():
    """Background loop: processes comment queue and fires riddles on idle."""
    global auto_reply_state

    while auto_reply_state["running"]:
        now = time.time()
        has_comment = len(auto_reply_state["comment_queue"]) > 0

        if has_comment:
            # Process all queued comments (FIFO)
            while auto_reply_state["comment_queue"]:
                username, comment = auto_reply_state["comment_queue"].pop(0)
                reply = gen_auto_reply(username, comment)

                # Render reply as ASCII art + emit
                ascii_reply = text_to_ascii(f"@{username}: {reply}", font=settings.get("font", "ansi_shadow"))
                payload = {
                    "type": "auto_reply",
                    "username": username,
                    "original_comment": comment,
                    "reply": reply,
                    "ascii_content": ascii_reply,
                    "timestamp": datetime.now().isoformat(),
                }
                state["active_display"] = {
                    "content": ascii_reply,
                    "type": "text",
                    "original_text": f"@{username}: {reply}",
                }
                socketio.emit("auto_reply_display", payload)
                speak_async(f"{username} bilang {reply}")

                # Update last comment time
                auto_reply_state["last_comment_time"] = time.time()

                # Reset riddle timer when there's activity
                if auto_reply_state["riddle_timer"]:
                    auto_reply_state["riddle_timer"].cancel()

                idle_sec = auto_reply_settings["idle_timeout_sec"]
                auto_reply_state["riddle_timer"] = threading.Timer(
                    idle_sec, _fire_riddle_ask
                )
                auto_reply_state["riddle_timer"].start()

                log("EVENT", "AUTO_REPLY", f"@{username}: {comment} → {reply}")
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

    r = gen_riddle()
    auto_reply_state["current_riddle"] = r

    ascii_q = text_to_ascii(r["q"], font=settings.get("font", "ansi_shadow"))
    payload = {
        "type": "riddle_ask",
        "question": r["q"],
        "ascii_content": ascii_q,
        "timestamp": datetime.now().isoformat(),
    }
    state["active_display"] = {
        "content": ascii_q,
        "type": "text",
        "original_text": r["q"],
    }
    socketio.emit("riddle_display", payload)
    speak_async(r["q"])
    log("EVENT", "AUTO_REPLY", f"RIDDLE ASK: {r['q']}")

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
    payload = {
        "type": "riddle_answer",
        "question": r["q"],
        "answer": r["a"],
        "ascii_content": ascii_a,
        "timestamp": datetime.now().isoformat(),
    }
    state["active_display"] = {
        "content": ascii_a,
        "type": "text",
        "original_text": f"Jawaban: {r['a']}",
    }
    socketio.emit("riddle_display", payload)
    speak_async(f"Jawabannya adalah {r['a']}")
    log("EVENT", "AUTO_REPLY", f"RIDDLE ANS: {r['a']}")

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

    cta_text = random.choice(CTAS)
    ascii_cta = text_to_ascii(cta_text, font=settings.get("font", "ansi_shadow"))
    payload = {
        "type": "cta",
        "content": cta_text,
        "ascii_content": ascii_cta,
        "timestamp": datetime.now().isoformat(),
        "tts_text": cta_text,  # TTS text for overlay to speak
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
    return jsonify(state)

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

    socketio.emit("display_update", {
        "content": content,
        "type": content_type,
        "source": "manual"
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
    log("EVENT", "TIKTOK", f"Connect requested to room: {room_id}")
    # Start TikTok connector in background
    state["tiktok_status"] = "CONNECTING"
    socketio.emit("status_update", {"tiktok_status": "CONNECTING"})
    threading.Thread(target=connect_tiktok, args=(room_id,), daemon=True).start()
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
    socketio.emit("riddle_display", {
        "type": "riddle_ask",
        "question": r["q"],
        "ascii_content": ascii_q,
        "timestamp": datetime.now().isoformat(),
    })
    # Fire answer after 5 seconds
    threading.Timer(5.0, lambda: socketio.emit("riddle_display", {
        "type": "riddle_answer",
        "question": r["q"],
        "answer": r["a"],
        "ascii_content": ascii_a,
        "timestamp": datetime.now().isoformat(),
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

def connect_tiktok(room_id):
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

    tiktok_conn = TikTokConnector(room_id, on_comment, on_gift)
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
    socketio.emit("display_update", {"content": None, "type": "none", "source": "clear"})
    return jsonify({"ok": True})

# ─── TELEGRAM BOT ───────────────────────────────────────────
telegram_bot = None

def init_telegram():
    """Initialize Telegram bot from .env config"""
    global telegram_bot
    from telegram_bot.bot import start_telegram_bot
    enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    if not enabled:
        log("INFO", "TELEGRAM", "Telegram trigger disabled (TELEGRAM_ENABLED=false)")
        return
    telegram_bot = start_telegram_bot()
    if telegram_bot:
        log("INFO", "TELEGRAM", "Telegram bot activated")

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
        socketio.emit("display_update", {
            "content": content,
            "type": state["active_display"]["type"],
            "source": "font_rotate",
            "font": next_font,
            "fontsize": settings["fontsize"]
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