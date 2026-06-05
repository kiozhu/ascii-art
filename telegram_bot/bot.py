"""
Telegram Bot Trigger for ASCII Overlay
======================================
Handles commands from Telegram to control the overlay.

Commands:
  /ascii status        → Show server status
  /ascii display <text>→ Display text on overlay
  /ascii big <text>    → Display big ASCII text
  /ascii block <text>  → Pixel block text
  /ascii half <text>   → Half-block shading
  /ascii clear         → Clear overlay
  /ascii tiktok <user> → Connect to TikTok
  /ascii image         → Send image to overlay (reply with photo)
  /ascii help          → Show available commands

Setup:
  1. Create bot via @BotFather → get bot token
  2. Get your chat ID via @userinfobot or @getidsbot
  3. Fill TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID in .env
"""

import os
import threading
import requests
from datetime import datetime

BASE_URL = f"http://localhost:{os.getenv('PORT', '5050')}"

# ─── Telegram Bot Setup ───────────────────────────────────
TELEGRAM_API = "https://api.telegram.org/bot{token}"

class TelegramBot:
    def __init__(self, token, admin_chat_id, command_prefix="ascii"):
        self.token = token
        self.admin_chat_id = admin_chat_id
        self.prefix = command_prefix
        self.offset = 0
        self._running = False
        self._last_msg = {}  # chat_id -> {text, msg_id}

    def send_message(self, chat_id, text, parse_mode="Markdown"):
        url = f"{TELEGRAM_API.format(token=self.token)}/sendMessage"
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

    def glitch_text(self, text):
        """Apply glitch effect: wide spaces + case toggle"""
        if not text:
            return ""
        normalized = text.replace(r'\s+', ' ')
        result = ''
        i = 0
        import random
        while i < len(normalized):
            char = normalized[i]
            r = random.random()
            if r < 0.4:
                glitch_chars = ['\u200B', '\u200C', '\u180E', '\u200D', '\u00AD']
                result += glitch_chars[random.randint(0, len(glitch_chars) - 1)]
                i += 1
            elif r < 0.8:
                result += char.upper() if char.islower() else char.lower()
            else:
                result += char
            i += 1
        return result.replace('  ', ' ').strip()

    def edit_message(self, chat_id, message_id, text, parse_mode=None):
        url = f"{TELEGRAM_API.format(token=self.token)}/editMessageText"
        try:
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

    def delete_message(self, chat_id, message_id):
        url = f"{TELEGRAM_API.format(token=self.token)}/deleteMessage"
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "message_id": message_id
            }, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

    def send_photo(self, chat_id, photo_url, caption=""):
        url = f"{TELEGRAM_API.format(token=self.token)}/sendPhoto"
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": caption
            }, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

    def handle_command(self, chat_id, text, msg_id=None, reply_to_msg=None):
        """Parse and execute commands"""
        text = text.strip()
        reply_to = reply_to_msg.get("message_id") if reply_to_msg else None

        if text == "/n":
            # Rotate font to next in pool — no reply needed
            import requests as r
            try:
                resp = r.post(f"{BASE_URL}/api/font/rotate", timeout=5).json()
                self.send_message(chat_id, f"🔄 Font: `{resp.get('font', 'unknown')}`")
            except Exception as e:
                self.send_message(chat_id, f"❌ Error: {e}")
            return

        if text.startswith(f"/{self.prefix}"):
            parts = text.split(" ", 2)
            cmd = parts[1] if len(parts) > 1 else "help"
            arg = parts[2] if len(parts) > 2 else ""

            if cmd == "status":
                self.cmd_status(chat_id)
            elif cmd == "display":
                if arg:
                    self.cmd_display(chat_id, arg)
                else:
                    self.send_message(chat_id, "Usage: `/ascii display <text>`")
            elif cmd == "big":
                if arg:
                    self.cmd_big(chat_id, arg)
                else:
                    self.send_message(chat_id, "Usage: `/ascii big <text>`")
            elif cmd == "block":
                if arg:
                    self.cmd_block(chat_id, arg)
                else:
                    self.send_message(chat_id, "Usage: `/ascii block <text>`")
            elif cmd == "half":
                if arg:
                    self.cmd_half(chat_id, arg)
                else:
                    self.send_message(chat_id, "Usage: `/ascii half <text>`")
            elif cmd == "clear":
                self.cmd_clear(chat_id)
            elif cmd == "tiktok":
                if arg:
                    self.cmd_tiktok(chat_id, arg)
                else:
                    self.send_message(chat_id, "Usage: `/ascii tiktok <username>`")
            elif cmd == "help":
                self.cmd_help(chat_id)
            else:
                self.send_message(chat_id, f"Unknown command: `{cmd}`. Try `/ascii help`")

        # Direct text without prefix (fallback)
        elif not text.startswith("/"):
            self.cmd_display(chat_id, text)

    def cmd_status(self, chat_id):
        import requests as r
        print(f"[TELEGRAM cmd_status] called for chat_id={chat_id}")
        try:
            resp = r.get(f"{BASE_URL}/api/status", timeout=5).json()
            print(f"[TELEGRAM cmd_status] status response: {resp}")
            uptime_info = "Running"
            msg = f"""*ASCII Overlay Status*

🟢 *Server:* {resp.get('server_status', 'N/A')}
📡 *TikTok:* {resp.get('tiktok_status', 'N/A')}
🎮 *Events:* {resp.get('event_count', 0)}
🔗 *Live ID:* {resp.get('live_id', '-')}
"""
            self.send_message(chat_id, msg)
        except:
            self.send_message(chat_id, "❌ Server offline atau tidak bisa diakses")

    def cmd_display(self, chat_id, text):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/display/manual", json={
                "content": text,
                "type": "text"
            }, timeout=5)
            self.send_message(chat_id, f"✅ Displayed:\n`{text[:200]}`")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_big(self, chat_id, text):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/display/manual", json={
                "content": text.upper(),
                "type": "bigtext"
            }, timeout=5)
            self.send_message(chat_id, f"✅ Big ASCII:\n`{text[:200].upper()}`")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_block(self, chat_id, text):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/display/manual", json={
                "content": text.upper(),
                "type": "block"
            }, timeout=5)
            self.send_message(chat_id, f"✅ Block:\n`{text[:200].upper()}`")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_half(self, chat_id, text):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/display/manual", json={
                "content": text.upper(),
                "type": "half"
            }, timeout=5)
            self.send_message(chat_id, f"✅ Half-block:\n`{text[:200].upper()}`")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_clear(self, chat_id):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/display/clear", timeout=5)
            self.send_message(chat_id, "🧹 Overlay cleared")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_tiktok(self, chat_id, username):
        import requests as r
        try:
            r.post(f"{BASE_URL}/api/tiktok/connect", json={
                "room_id": username
            }, timeout=5)
            self.send_message(chat_id, f"🔗 Connecting to TikTok: `@{username}`...")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def cmd_help(self, chat_id):
        msg = """*ASCII Overlay - Commands*

`/ascii status` — Server status
`/ascii display <text>` — Show text on overlay
`/ascii big <text>` — Big ASCII text
`/ascii block <text>` — Pixel block text
`/ascii half <text>` — Half-block shading
`/ascii clear` — Clear overlay
`/ascii tiktok <user>` — Connect TikTok
`/ascii help` — This menu

*Direct text* — Just type to display it

*Reply with photo* — Send image to overlay"""
        self.send_message(chat_id, msg)

    def handle_photo(self, chat_id, file_id, caption=""):
        """Handle photo attachment - download and send to overlay"""
        url = f"{TELEGRAM_API.format(token=self.token)}/getFile"
        try:
            resp = requests.get(url, params={"file_id": file_id}, timeout=10).json()
            if resp.get("ok"):
                file_path = resp["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                # Send to overlay as image
                import requests as r
                r.post(f"{BASE_URL}/api/display/manual", json={
                    "content": file_url,
                    "type": "image"
                }, timeout=10)
                self.send_message(chat_id, "🖼️ Image sent to overlay")
        except Exception as e:
            self.send_message(chat_id, f"❌ Error: {e}")

    def poll(self):
        """Poll Telegram for updates"""
        url = f"{TELEGRAM_API.format(token=self.token)}/getUpdates"
        import sys
        print(f"[TELEGRAM POLL] Started!", flush=True)
        sys.stdout.flush()
        iteration = 0
        while self._running:
            iteration += 1
            try:
                print(f"[TELEGRAM POLL] iteration={iteration} offset={self.offset} making request...", flush=True)
                resp = requests.get(url, params={
                    "offset": self.offset,
                    "timeout": 30
                }, timeout=35)
                print(f"[TELEGRAM POLL] resp status={resp.status_code} len={len(resp.content)} bytes", flush=True)
                d = resp.json()
                print(f"[TELEGRAM POLL] resp ok={d.get('ok')} results={len(d.get('result',[]))}", flush=True)

                if not d.get("ok"):
                    print(f"[TELEGRAM POLL] not ok: {d}")
                    break

                updates = d.get("result", [])
                if updates:
                    print(f"[TELEGRAM POLL] Got {len(updates)} updates!", flush=True)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    chat_id = str(chat.get("id", ""))

                    if self.admin_chat_id and chat_id != str(self.admin_chat_id):
                        print(f"[TELEGRAM POLL] Ignoring non-admin {chat_id}", flush=True)
                        continue

                    text = message.get("text", "")
                    photo = message.get("photo", [])
                    reply_to = message.get("reply_to_message")

                    print(f"[TELEGRAM POLL] Processing: text={repr(text)[:50]}", flush=True)

                    if text and not text.startswith('/'):
                        self._last_msg[chat_id] = {"text": text, "msg_id": message.get("message_id")}

                    if text:
                        self.handle_command(chat_id, text, message.get("message_id"), reply_to)
                    elif photo:
                        best_photo = max(photo, key=lambda p: p.get("file_size", 0))
                        self.handle_photo(chat_id, best_photo["file_id"])
                else:
                    print(f"[TELEGRAM POLL] No updates, waiting...", flush=True)

            except requests.exceptions.ReadTimeout:
                print("[TELEGRAM POLL] ReadTimeout, continuing", flush=True)
                continue
            except Exception as e:
                print(f"[TELEGRAM POLL ERROR] {e}")
                import time
                time.sleep(5)

    def start(self):
        self._running = True
        t = threading.Thread(target=self.poll, daemon=True)
        t.start()
        print(f"[TELEGRAM] Bot started")

    def stop(self):
        self._running = False
        print(f"[TELEGRAM] Bot stopped")


def start_telegram_bot(bot_token=None, admin_chat_id=None, command_prefix=None):
    """Initialize and start Telegram bot — accepts runtime config or falls back to .env"""
    # Runtime overrides; if not provided, read from environment
    token = bot_token if bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = admin_chat_id if admin_chat_id is not None else os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    prefix = command_prefix if command_prefix is not None else os.getenv("TELEGRAM_COMMAND_PREFIX", "ascii").strip()

    if not token or token == "***":
        print("[TELEGRAM] No bot token configured")
        return None

    admin_chat_id_int = None
    if admin_id is not None:
        if isinstance(admin_id, int):
            admin_chat_id_int = admin_id
        elif isinstance(admin_id, str) and admin_id.isdigit():
            admin_chat_id_int = int(admin_id)
    bot = TelegramBot(token, admin_chat_id_int, prefix)
    bot.start()
    return bot


def stop_telegram_bot(bot):
    if bot:
        bot.stop()