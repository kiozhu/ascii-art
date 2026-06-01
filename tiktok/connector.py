"""
TikTok Live Connector using TikTokLive library
===============================================
pip install TikTokLive

⚠️ NOTE: TikTok may rate-limit or block accounts that use
third-party libraries to access live data. Use at your own risk.
For production, consider running through a proxy server.
"""

import asyncio
import threading
from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import CommentEvent, GiftEvent, LikeEvent, FollowEvent

class TikTokConnector:
    def __init__(self, room_id, on_comment_callback, on_gift_callback=None):
        self.room_id = room_id
        self.on_comment = on_comment_callback
        self.on_gift = on_gift_callback or (lambda *args: None)
        self.client: TikTokLiveClient = None
        self._thread = None
        self._running = False

    def connect(self):
        """Start TikTok live listener in background thread"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            # Extract unique_id from room_id if it's a URL
            unique_id = self._parse_room_id()

            self.client = TikTokLiveClient(
                unique_id=unique_id,
                **({
                    "connect_options": {
                        "enable_extended_gift_info": True,
                    }
                } if hasattr(TikTokLiveClient, 'connect_options') else {})
            )

            # Register event handlers
            @self.client.on("comment")
            def handle_comment(event: CommentEvent):
                username = getattr(event, "user", {}) or {}
                if hasattr(username, 'nickname'):
                    name = username.nickname
                elif hasattr(event, 'commenter'):
                    name = getattr(event, 'commenter', 'unknown')
                else:
                    name = str(username) if username else "unknown"
                # Fallback: try common attribute paths
                if name == "unknown" or not name:
                    for attr in ["user.nickname", "commenter.nickname", "author", "user.display_name"]:
                        try:
                            name = str(getattr(event, attr, ""))
                            if name and name != "None":
                                break
                        except:
                            pass
                comment = getattr(event, "comment", "") or getattr(event, "text", "") or ""
                if comment:
                    self.on_comment(name or "unknown", comment)

            @self.client.on("gift")
            def handle_gift(event):
                user = getattr(event, "user", {}) or {}
                name = getattr(user, "nickname", str(user)) if user else "unknown"
                gift_name = getattr(event, "gift_name", "gift") or "gift"
                self.on_gift(name, gift_name)

            # Start client
            self.client.run()
        except Exception as e:
            print(f"[TIKTOK ERROR] {e}")
            self._running = False

    def _parse_room_id(self):
        """Extract username/unique_id from room_id or URL"""
        import re
        # If it's a URL like https://www.tiktok.com/@username/live
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
            except:
                pass
        self._running = False