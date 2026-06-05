"""
TikTok Live Connector using TikTokLive library
===============================================
pip install TikTokLive

Callbacks for status propagation:
  - on_connect_callback(uid, room_id) → called when successfully connected
  - on_error_callback(msg)            → called with error message on failure
  - on_status_callback(status)        → called for status updates
  - on_disconnect_callback()          → called when disconnected

⚠️ NOTE: TikTok may rate-limit or block accounts that use
third-party libraries to access live data. Use at your own risk.
For production, consider running through a proxy server.
"""

import sys
import threading
import time
import traceback
import logging
import re as _re

# Module-level logger that writes to stderr (server captures these)
logger = logging.getLogger("tiktok_connector")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] [TIKTOK] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

from TikTokLive import TikTokLiveClient
# CORRECT import path: errors live in TikTokLive.client.errors (NOT TikTokLive.types.errors)
from TikTokLive.client.errors import (
    LiveNotFound, LiveEnded, DuplicateClientError,
    UserNotFoundError, UserOfflineError, SignatureRateLimitError,
)
# CORRECT import path: events live in TikTokLive.events (NOT TikTokLive.types.events)
from TikTokLive.events import (
    CommentEvent, GiftEvent, LikeEvent, FollowEvent,
    ConnectEvent, DisconnectEvent, LiveEndEvent, ShareEvent, JoinEvent,
)


class TikTokConnector:
    def __init__(
        self,
        room_id,
        on_comment_callback,
        on_gift_callback=None,
        on_connect_callback=None,
        on_error_callback=None,
        on_status_callback=None,
        on_disconnect_callback=None,
        on_retry_callback=None,
        web_proxy=None,
        ws_proxy=None,
        max_retries=3,
        retry_delay=5.0,
    ):
        self.room_id = room_id
        self.on_comment = on_comment_callback
        self.on_gift = on_gift_callback or (lambda *args: None)
        self.on_connect = on_connect_callback or (lambda *args: None)
        self.on_error = on_error_callback or (lambda *args: None)
        self.on_status = on_status_callback or (lambda *args: None)
        self.on_disconnect = on_disconnect_callback or (lambda *args: None)
        self.on_retry = on_retry_callback or (lambda *args: None)
        self.web_proxy = web_proxy
        self.ws_proxy = ws_proxy
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client: TikTokLiveClient = None
        self._thread = None
        self._running = False
        self._retry_count = 0

    def connect(self):
        """Start TikTok live listener in background thread"""
        if self._thread and self._thread.is_alive():
            logger.warning("Connect called but thread already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._retry_count = 0
        unique_id = self._parse_room_id()
        logger.info(f"Resolving user: {unique_id}")
        self.on_status(f"RESOLVING:{unique_id}")

        while self._running and self._retry_count < self.max_retries:
            try:
                self.client = TikTokLiveClient(
                    unique_id=unique_id,
                    web_proxy=self.web_proxy,
                    ws_proxy=self.ws_proxy,
                )

                # ── Event handlers (using real proto field names) ──

                @self.client.on(CommentEvent)
                def handle_comment(event: CommentEvent):
                    # WebcastChatMessage: user_info (User), content (str)
                    user = getattr(event, "user_info", None) or getattr(event, "user", None)
                    comment = (
                        getattr(event, "content", None)
                        or getattr(event, "comment", None)
                        or getattr(event, "text", None)
                    )
                    username = self._user_display_name(user) if user else "unknown"
                    if comment and str(comment).strip():
                        text = str(comment).strip()
                        logger.info(f"Comment from @{username}: {text!r}")
                        self.on_comment(username, text)

                @self.client.on(GiftEvent)
                def handle_gift(event: GiftEvent):
                    # WebcastGiftMessage: from_user (User), m_gift (Gift)
                    user = (
                        getattr(event, "from_user", None)
                        or getattr(event, "user", None)
                    )
                    name = self._user_display_name(user) if user else "unknown"
                    gift_obj = (
                        getattr(event, "m_gift", None)
                        or getattr(event, "gift", None)
                    )
                    if gift_obj and getattr(gift_obj, "name", None):
                        gift_name = gift_obj.name
                    else:
                        gift_name = (
                            getattr(event, "gift_name", None)
                            or getattr(event, "describe", "gift")
                            or "gift"
                        )
                    repeat = getattr(event, "repeat_count", 1) or 1
                    logger.info(f"Gift from @{name}: {gift_name} x{repeat}")
                    self.on_gift(name, f"{gift_name} x{repeat}" if repeat > 1 else gift_name)

                @self.client.on(LikeEvent)
                def handle_like(event: LikeEvent):
                    user = getattr(event, "user", None)
                    name = self._user_display_name(user) if user else "unknown"
                    count = getattr(event, "count", 1) or 1
                    logger.info(f"Like from @{name} x{count}")

                @self.client.on(FollowEvent)
                def handle_follow(event: FollowEvent):
                    user = getattr(event, "user", None)
                    name = self._user_display_name(user) if user else "unknown"
                    logger.info(f"Follow: @{name}")
                    self.on_comment(name, "🎉 baru follow!")

                @self.client.on(JoinEvent)
                def handle_join(event: JoinEvent):
                    user = getattr(event, "user", None)
                    name = self._user_display_name(user) if user else "unknown"
                    logger.info(f"Join: @{name}")

                @self.client.on(ShareEvent)
                def handle_share(event: ShareEvent):
                    user = getattr(event, "user", None)
                    name = self._user_display_name(user) if user else "unknown"
                    logger.info(f"Share: @{name}")

                @self.client.on(ConnectEvent)
                def handle_connect(event: ConnectEvent):
                    logger.info(f"Connected! room_id={event.room_id}")
                    self.on_status(f"CONNECTED:{event.unique_id}")
                    self.on_connect(event.unique_id, event.room_id)

                @self.client.on(DisconnectEvent)
                def handle_disconnect(event: DisconnectEvent):
                    logger.info("Disconnected from live")
                    self.on_status("DISCONNECTED")
                    self.on_disconnect()

                @self.client.on(LiveEndEvent)
                def handle_live_end(event: LiveEndEvent):
                    logger.info("Live ended")
                    self.on_status("LIVE_ENDED")
                    self.on_disconnect()

                # Start client — blocks until disconnected
                self.on_status(f"CONNECTING:{unique_id}")
                logger.info(f"Connecting to @{unique_id}...")
                self.client.run()

                logger.info("client.run() returned cleanly")
                break

            except LiveNotFound:
                self._retry_count += 1
                err = f"Live not found for @{unique_id}"
                logger.error(err)
                self.on_error(f"LiveNotFound: {err}")
                self.on_status("ERROR")
                self._running = False
                return

            except LiveEnded:
                self._retry_count += 1
                err = "Live stream has ended"
                logger.error(err)
                self.on_error(f"LiveEnded: {err}")
                self.on_status("LIVE_ENDED")
                self._running = False
                return

            except DuplicateClientError:
                self._retry_count += 1
                err = "Duplicate client — another connection may be active"
                logger.error(err)
                self.on_error(f"DuplicateClient: {err}")
                self.on_status("ERROR")
                self._running = False
                return

            except (UserNotFoundError, UserOfflineError) as e:
                # User doesn't exist or not streaming — don't retry
                self._retry_count += 1
                err = f"{type(e).__name__}: {e}"
                logger.error(f"User error: {err}")
                self.on_error(err)
                self.on_status("ERROR")
                self._running = False
                return

            except SignatureRateLimitError as e:
                # TikTok is rate-limiting our signature fetch — wait longer
                self._retry_count += 1
                err = f"SignatureRateLimit: {e}"
                logger.error(err)
                self.on_error(err)
                if self._retry_count >= self.max_retries:
                    self.on_status("ERROR")
                    self._running = False
                    return
                self.on_retry(self._retry_count, err)
                self.on_status(f"RETRYING:{self._retry_count}/{self.max_retries}")
                time.sleep(self.retry_delay * 2)  # longer wait on rate limit

            except Exception as e:
                self._retry_count += 1
                error_msg = traceback.format_exc()
                logger.error(
                    f"Attempt {self._retry_count}/{self.max_retries} failed: {e}\n{error_msg}"
                )
                # Always notify the app of errors so the status can move off CONNECTING
                self.on_error(f"{type(e).__name__}: {e}")
                if self._retry_count >= self.max_retries:
                    self.on_status("ERROR")
                    self._running = False
                    logger.error(f"All {self.max_retries} retries exhausted. Giving up.")
                    return
                self.on_retry(self._retry_count, str(e))
                self.on_status(f"RETRYING:{self._retry_count}/{self.max_retries}")
                time.sleep(self.retry_delay)

    @staticmethod
    def _user_display_name(user) -> str:
        """Extract display name from various user object shapes.

        TikTokLive's User proto has `nick_name` (snake_case), not `nickname`.
        We still fall back to the camelCase variant for forward-compat.
        """
        if not user:
            return "unknown"
        for attr in ("nick_name", "nickname", "display_name", "unique_id", "name"):
            val = getattr(user, attr, None)
            if val:
                return str(val)
        return str(user) if str(user) and str(user) != "None" else "unknown"

    def _parse_room_id(self):
        """Extract username/unique_id from room_id or URL"""
        if "/" in str(self.room_id):
            match = _re.search(r"@([^/]+)", str(self.room_id))
            if match:
                return match.group(1)
        return str(self.room_id).lstrip("@")

    def disconnect(self):
        self._running = False
        if self.client:
            try:
                self.client.stop()
            except Exception:
                pass
        self.on_status("DISCONNECTED")
        self._running = False
