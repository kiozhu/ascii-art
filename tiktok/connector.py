"""
TikTok Live Connector using piratetok-live-py
==============================================
Library: https://github.com/PirateTok/live-py

Advantages over TikTokLive v6.6.5:
- No sign server required (Euler down pun jalan)
- No API key required
- No Playwright/cookies needed
- Uses curl_cffi to bypass TikTok WAF
- Stable connection (5+ minutes tested)
- Simple API (~10 lines vs 669 lines)

pip install piratetok-live-py
"""

import asyncio
import threading
import logging

logger = logging.getLogger("tiktok_connector")

# Import piratetok-live-py
try:
    from piratetok_live import TikTokLiveClient, EventType
    PIRATETOK_AVAILABLE = True
except ImportError:
    PIRATETOK_AVAILABLE = False
    logger.error("piratetok-live-py not installed. Run: pip install piratetok-live-py")


class TikTokConnector:
    def __init__(
        self,
        room_id,
        on_comment_callback,
        on_gift_callback=None,
        on_connect_callback=None,
        on_error_callback=None,
        on_disconnect_callback=None,
        on_retry_callback=None,
        on_status_callback=None,
        web_proxy=None,
        ws_proxy=None,
        max_retries=3,
        retry_delay=5.0,
    ):
        self.room_id = room_id
        self.on_comment = on_comment_callback
        self.on_gift = on_gift_callback or (lambda *a, **k: None)
        self.on_connect = on_connect_callback or (lambda *a, **k: None)
        self.on_error = on_error_callback or (lambda *a: None)
        self.on_disconnect = on_disconnect_callback or (lambda: None)
        self.on_retry = on_retry_callback or (lambda *a, **k: None)
        self.on_status = on_status_callback or (lambda s: None)
        self.web_proxy = web_proxy
        self.ws_proxy = ws_proxy
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._thread = None
        self._running = False
        self._client = None
        self._loop = None
        self._retry_count = 0
        self._connected = False

    def connect(self):
        """Start TikTok live listener in background thread"""
        if not PIRATETOK_AVAILABLE:
            self.on_error("piratetok-live-py not installed")
            self.on_status("ERROR")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """Background thread that runs the async event loop"""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_run())
        except Exception as e:
            logger.error(f"Thread error: {e}")
            self.on_error(f"{type(e).__name__}: {e}")
            self.on_status("ERROR")

    async def _async_run(self):
        """Async run with retry logic"""
        # Strip @ if present
        username = self.room_id.lstrip('@').strip()

        while self._running and self._retry_count < self.max_retries:
            try:
                if self._retry_count > 0:
                    self.on_retry(self._retry_count, "reconnecting")
                    self.on_status(f"RETRYING:{self._retry_count}/{self.max_retries}")
                    await asyncio.sleep(self.retry_delay * self._retry_count)

                logger.info(f"Creating TikTokLiveClient for @{username}")
                self._client = TikTokLiveClient(username)

                # Register event handlers
                self._client.on(EventType.chat)(self._handle_chat)
                self._client.on(EventType.gift)(self._handle_gift)
                self._client.on(EventType.like)(self._handle_like)
                self._client.on(EventType.follow)(self._handle_follow)
                self._client.on(EventType.share)(self._handle_share)
                self._client.on(EventType.join)(self._handle_join)
                # subscribe → subscription_notify in piratetok
                if hasattr(EventType, 'subscription_notify'):
                    self._client.on(EventType.subscription_notify)(self._handle_subscribe)

                self.on_status(f"CONNECTING:{username}")
                logger.info(f"Connecting to @{username}...")

                # Mark as connected once connect starts
                self._connected = True
                try:
                    self.on_connect(username, username)  # (unique_id, room_id)
                except TypeError:
                    try:
                        self.on_connect(username)  # (unique_id)
                    except TypeError:
                        pass
                self.on_status(f"CONNECTED:{username}")

                # This blocks until disconnected
                await self._client.connect()

                # If we get here, client disconnected cleanly
                logger.info("Client disconnected cleanly")
                self._connected = False
                self.on_disconnect()
                break

            except Exception as e:
                self._retry_count += 1
                err = f"{type(e).__name__}: {e}"
                logger.error(f"Connection error: {err}")
                self.on_error(err)

                if self._retry_count >= self.max_retries:
                    self.on_status("ERROR")
                    self._running = False
                    return

    def _handle_chat(self, evt):
        """Handle chat/comment event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            nickname = user_info.get("nickname", username)
            comment = data.get("content", "")
            if comment:
                logger.info(f"Comment from @{username}: {comment}")
                # Try multiple signatures for compatibility
                try:
                    self.on_comment(username, comment)
                except TypeError:
                    try:
                        self.on_comment(username, nickname, comment)
                    except TypeError:
                        # app.py signature: on_comment(username, comment)
                        self.on_comment(username, comment)
        except Exception as e:
            logger.error(f"Error handling chat: {e}")

    def _handle_gift(self, evt):
        """Handle gift event — trigger gift animation via app.py"""
        try:
            data = evt.data
            # piratetok-live-py gift structure:
            # data.user.uniqueId, data.user.nickname
            # data.gift.name, data.gift.diamond_count, data.gift.describe
            # data.repeat_count, data.combo_count
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            nickname = user_info.get("nickname", username)
            gift_info = data.get("gift", {})
            gift_name = gift_info.get("name", "unknown")
            diamond_count = gift_info.get("diamondCount", 0)
            repeat_count = data.get("repeatCount", 1)
            combo_count = data.get("comboCount", 1)
            logger.info(f"Gift from @{username}: {gift_name} x{repeat_count} ({diamond_count} diamonds)")
            # Call gift callback (app.py on_gift handles emit + animation)
            try:
                self.on_gift(username, gift_name)
            except TypeError:
                try:
                    self.on_gift(username, nickname, gift_name, repeat_count, diamond_count)
                except TypeError:
                    self.on_gift(username, gift_name)
        except Exception as e:
            logger.error(f"Error handling gift: {e}")

    def _handle_like(self, evt):
        """Handle like event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            total = data.get("total", 0)
            logger.debug(f"Like from @{username}: {total} total")
        except Exception as e:
            logger.error(f"Error handling like: {e}")

    def _handle_follow(self, evt):
        """Handle follow event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            logger.info(f"Follow from @{username}")
        except Exception as e:
            logger.error(f"Error handling follow: {e}")

    def _handle_share(self, evt):
        """Handle share event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            logger.info(f"Share from @{username}")
        except Exception as e:
            logger.error(f"Error handling share: {e}")

    def _handle_join(self, evt):
        """Handle join event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            logger.debug(f"Join: @{username}")
        except Exception as e:
            logger.error(f"Error handling join: {e}")

    def _handle_subscribe(self, evt):
        """Handle subscribe event"""
        try:
            data = evt.data
            user_info = data.get("user", {})
            username = user_info.get("uniqueId") or user_info.get("nickname", "unknown")
            logger.info(f"Subscribe from @{username}")
        except Exception as e:
            logger.error(f"Error handling subscribe: {e}")

    def on_status(self, status):
        """Status callback (set by app.py)"""
        if hasattr(self, '_status_callback') and self._status_callback:
            self._status_callback(status)
        else:
            logger.info(f"Status: {status}")

    def disconnect(self):
        """Stop the connector"""
        self._running = False
        if self._client and self._loop:
            try:
                # Schedule disconnect in the event loop
                future = asyncio.run_coroutine_threadsafe(
                    self._client.disconnect() if hasattr(self._client, 'disconnect') else self._async_disconnect(),
                    self._loop
                )
                future.result(timeout=5)
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False

    async def _async_disconnect(self):
        """Async disconnect helper"""
        if self._client and hasattr(self._client, 'disconnect'):
            await self._client.disconnect()
