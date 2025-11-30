import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal

from winrt.windows.media.control import \
    GlobalSystemMediaTransportControlsSessionManager, \
    GlobalSystemMediaTransportControlsSessionPlaybackStatus
    
try:
    from winrt.windows.storage.streams import DataReader
    HAS_STREAMS = True
except ImportError:
    HAS_STREAMS = False


class MediaWorker(QObject):
    """Background worker for fetching media information from Windows."""
    
    metadata_updated = pyqtSignal(str, str, bool, float, float, bytes) 

    def __init__(self):
        super().__init__()
        self.running = True
        self.loop = asyncio.new_event_loop()
        self.current_session = None

    def start(self):
        """Start the background polling thread."""
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        """Run the asyncio event loop in a separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_media())

    async def _poll_media(self):
        """Poll media information every 0.5 seconds."""
        while self.running:
            try:
                manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                session = manager.get_current_session()
                self.current_session = session

                if session:
                    info = session.get_playback_info()
                    is_playing = info.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
                    props = await session.try_get_media_properties_async()
                    title = props.title if props.title else "Unknown"
                    artist = props.artist if props.artist else ""
                    
                    timeline = session.get_timeline_properties()
                    pos_sec = timeline.position.total_seconds() if timeline else 0.0
                    dur_sec = timeline.end_time.total_seconds() if timeline else 0.0
                    
                    img_data = b""
                    if HAS_STREAMS and props.thumbnail:
                        try:
                            stream = await props.thumbnail.open_read_async()
                            size = stream.size
                            if size > 0:
                                reader = DataReader(stream)
                                await reader.load_async(size)
                                buf = bytearray(size)
                                reader.read_bytes(buf)
                                img_data = bytes(buf)
                        except:
                            pass
                    
                    self.metadata_updated.emit(title, artist, is_playing, pos_sec, dur_sec, img_data)
                else:
                    self.metadata_updated.emit("Idle", "", False, 0.0, 0.0, b"")
            except:
                pass
            
            await asyncio.sleep(0.5) 

    def toggle_media(self):
        """Toggle play/pause."""
        if self.current_session:
            asyncio.run_coroutine_threadsafe(self._toggle_async(), self.loop)
    
    def next_track(self):
        """Skip to next track."""
        if self.current_session:
            asyncio.run_coroutine_threadsafe(self._next_async(), self.loop)
    
    def prev_track(self):
        """Skip to previous track."""
        if self.current_session:
            asyncio.run_coroutine_threadsafe(self._prev_async(), self.loop)
    
    def seek_to(self, seconds):
        """Seek to a specific position in seconds."""
        if self.current_session:
            asyncio.run_coroutine_threadsafe(self._seek_async(seconds), self.loop)

    async def _toggle_async(self):
        try:
            await self.current_session.try_toggle_play_pause_async()
        except:
            pass
    
    async def _next_async(self):
        try:
            await self.current_session.try_skip_next_async()
        except:
            pass
    
    async def _prev_async(self):
        try:
            await self.current_session.try_skip_previous_async()
        except:
            pass
    
    async def _seek_async(self, seconds):
        try:
            ticks = int(seconds * 10_000_000)
            await self.current_session.try_change_playback_position_async(ticks) 
        except:
            pass