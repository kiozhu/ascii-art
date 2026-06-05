"""
TikTok Live Connector using TikTokLive library
===============================================
pip install TikTokLive

Callbacks for status propagation:
  - on_connect_callback()    → called when successfully connected
  - on_error_callback(msg)  → called with error message on failure
  - on_retry_callback(count) → called before each retry attempt

⚠️ NOTE: TikTok may rate-limit or block accounts that use
third-party libraries to access live data. Use at your own risk.
For production, consider running through a proxy server.
"""

import asyncio
import threading
import time
from TikTokLive import TikTokLiveClient
from TikTokLive.types.errors import LiveNotFound, LiveEnded, DuplicateClientError

class TikTokConnector:
    def __init__(
        self,
        room_id,
        on_comment_callback,
        on_gift_callback=None,
        on_connect_callback=None,
        on_error_callback=None,
        on_retry_callback=None,
        web_proxy=None,
        ws_proxy=None,
        max_retries=3,
        retry_delay=5.0,
    ):
        self.room_id = room_id
        self.on_comment = on_comment_callback
        self.on_gift = on_gift_callback or (lambda *args: None)
        self.on_connect = on_connect_callback or (lambda: None)
        self.on_error = on_error_callback or (lambda *args: None)
        self.on_retry = on_retry_callback or (lambda *args: None)
        self.web_proxy = web_proxy
        self.ws_proxy = ws_proxy
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client: TikTokLiveClient = None
        self._thread = None
        self._running = False

    def connect(self):
        """Start TikTok live listener in background thread"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        attempt = 0
        last_error = None

        while self._running and attempt < self.max_retries:
            attempt += 1
            if attempt > 1:
                self.on_retry(attempt, last_error)
                time.sleep(self.retry_delay)

            try:
                unique_id = self._parse_room_id()
                extra_kwargs = (
                    {"connect_options": {"enable_extended_gift_info": True}}
                    if hasattr(TikTokLiveClient, "connect_options")
                    else {}
                )
                self.client = TikTokLiveClient(
                    unique_id=unique_id,
                    web_proxy=self.web_proxy,
                    ws_proxy=self.ws_proxy,
                    **extra_kwargs,
                )

                # Register event handlers
                @self.client.on("comment")
                def handle_comment(event):
                    username = getattr(event, "user", {}) or {}
                    if hasattr(username, "nickname"):
                        name = username.nickname
                    elif hasattr(event, "commenter"):
                        name = getattr(event, "commenter", "unknown")
                    else:
                        name = str(username) if username else "unknown"
                    if name == "unknown" or not name:
                        for attr in [
                            "user.nickname",
                            "commenter.nickname",
                            "author",
                            "user.display_name",
                        ]:
                            try:
                                name = str(getattr(event, attr, ""))
                                if name and name != "None":
                                    break
                            except Exception:
                                pass
                    comment = getattr(event, "comment", "") or getattr(
                        event, "text", ""
                    ) or ""
                    if comment:
                        self.on_comment(name or "unknown", comment)

                @self.client.on("gift")
                def handle_gift(event):
                    user = getattr(event, "user", {}) or {}
                    name = (
                        getattr(user, "nickname", str(user))
                        if user
                        else "unknown"
                    )
                    gift_name = getattr(event, "gift_name", "gift") or "gift"
                    self.on_gift(name, gift_name)

                # Start client — this blocks until disconnected
                self.client.run()
                # If run() returns normally, stream ended
                if self._running:
                    last_error = "Live stream ended or was disconnected"
                    self.on_error("Live stream ended")
                    break

            except LiveNotFound:
                last_error = f"Live not found: @{unique_id}"
                self.on_error(f"Live not found for @{unique_id}")
                break  # Don't retry if room doesn't exist

            except LiveEnded:
                last_error = "Live stream has ended"
                self.on_error("Live stream has ended")
                break  # Don't retry if stream ended

            except DuplicateClientError:
                last_error = "Duplicate client error — another connection active"
                self.on_error("Duplicate client — another connection may be active")
                break

            except Exception as e:
                last_error = str(e)
                if self._running:
                    self.on_error(f"Connection error: {e}")
                    # Will retry if attempts remain
                # If not running, we were stopped intentionally — don't retry

        if self._running and attempt >= self.max_retries:
            self.on_error(f"Failed after {attempt} attempts: {last_error}")

        self._running = False

    def _parse_room_id(self):
        """Extract username/unique_id from room_id or URL"""
        import re

        if "/" in str(self.room_id):
            match = re.search(r"@([^/]+)", str(self.room_id))
            if match:
                return match.group(1)
        return str(self.room_id)

    def disconnect(self):
        self._running = False
        if self.client:
            try:
                self.client.stop()
            except Exception:
                pass
        self._running = False
