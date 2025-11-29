import sys
import asyncio
import threading
import time
import os
import math
import random
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QFont, QPen, QAction, QIcon, QPixmap, QPainterPath, QLinearGradient

# WinRT Imports
from winrt.windows.media.control import \
    GlobalSystemMediaTransportControlsSessionManager, \
    GlobalSystemMediaTransportControlsSessionPlaybackStatus
    
try:
    from winrt.windows.storage.streams import DataReader
    HAS_STREAMS = True
except ImportError:
    HAS_STREAMS = False

# --- Configuration ---
IDLE_W, IDLE_H = 200, 35        
HOVER_W, HOVER_H = 230, 42      
EXPAND_W, EXPAND_H = 450, 190

CORNER_RADIUS = 800              
SPRING_STIFFNESS = 0.15
SPRING_DAMPING = 0.62

BARYPOS = 70
BTNYPOS = 40

COLOR_BG = QColor("#000000")
COLOR_ACCENT = QColor("#FFFFFF") 
COLOR_PAUSED = QColor("#FF9500")
COLOR_TEXT_MAIN = QColor("#FFFFFF")
COLOR_TEXT_SUB = QColor("#DDDDDD")
COLOR_BAR_BG = QColor(255, 255, 255, 50)

IMG_PLAY_FILE = "play.png"
IMG_PAUSE_FILE = "pause.png"
IMG_NEXT_FILE = "next.png"
IMG_PREV_FILE = "prev.png"

# --- Helpers ---
def load_or_create_icon(filename, fallback_name, size=40, color=Qt.GlobalColor.white):
    if os.path.exists(filename):
        pixmap = QPixmap(filename)
        if not pixmap.isNull():
            return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    
    center = size / 2
    if fallback_name == "play":
        path = QPainterPath()
        path.moveTo(center - 6, center - 10)
        path.lineTo(center + 10, center)
        path.lineTo(center - 6, center + 10)
        path.closeSubpath()
        p.drawPath(path)
    elif fallback_name == "pause":
        p.drawRect(int(center - 8), int(center - 10), 6, 20)
        p.drawRect(int(center + 2), int(center - 10), 6, 20)
    elif fallback_name == "next":
        path = QPainterPath()
        path.moveTo(center - 6, center - 10)
        path.lineTo(center + 6, center)
        path.lineTo(center - 6, center + 10)
        p.drawPath(path)
        p.drawRect(int(center + 6), int(center - 10), 3, 20)
    elif fallback_name == "prev":
        path = QPainterPath()
        path.moveTo(center + 6, center - 10)
        path.lineTo(center - 6, center)
        path.lineTo(center + 6, center + 10)
        p.drawPath(path)
        p.drawRect(int(center - 9), int(center - 10), 3, 20)
    p.end()
    return pixmap

# --- Background Worker ---
class MediaWorker(QObject):
    metadata_updated = pyqtSignal(str, str, bool, float, float, bytes) 

    def __init__(self):
        super().__init__()
        self.running = True
        self.loop = asyncio.new_event_loop()
        self.current_session = None

    def start(self):
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_media())

    async def _poll_media(self):
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
                        except: pass
                    
                    self.metadata_updated.emit(title, artist, is_playing, pos_sec, dur_sec, img_data)
                else:
                    self.metadata_updated.emit("Idle", "", False, 0.0, 0.0, b"")
            except: pass
            
            # [FIX] Reduced poll time to 0.5s for slightly faster syncing, 
            # but relies on local timer for smoothness
            await asyncio.sleep(0.5) 

    def toggle_media(self):
        if self.current_session: asyncio.run_coroutine_threadsafe(self._toggle_async(), self.loop)
    def next_track(self):
        if self.current_session: asyncio.run_coroutine_threadsafe(self._next_async(), self.loop)
    def prev_track(self):
        if self.current_session: asyncio.run_coroutine_threadsafe(self._prev_async(), self.loop)
    def seek_to(self, seconds):
        if self.current_session: asyncio.run_coroutine_threadsafe(self._seek_async(seconds), self.loop)

    async def _toggle_async(self):
        try: await self.current_session.try_toggle_play_pause_async()
        except: pass
    async def _next_async(self):
        try: await self.current_session.try_skip_next_async()
        except: pass
    async def _prev_async(self):
        try: await self.current_session.try_skip_previous_async()
        except: pass
    async def _seek_async(self, seconds):
        try:
            ticks = int(seconds * 10_000_000)
            await self.current_session.try_change_playback_position_async(ticks) 
        except: pass

# --- Main UI ---
class DynamicIsland(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.screen_width = QApplication.primaryScreen().size().width()
        
        # Physics State
        self.current_w = float(IDLE_W)
        self.current_h = float(IDLE_H)
        self.target_w = float(IDLE_W)
        self.target_h = float(IDLE_H)
        self.vel_w = 0.0
        self.vel_h = 0.0
        
        # Button Animation State
        self.btn_anim = {
            'play': {'scale': 0.2, 'offset': 0.0},
            'prev': {'scale': 0.2, 'offset': 0.0},
            'next': {'scale': 0.2, 'offset': 0.0}
        }
        
        # Visualizer State
        self.vis_count = 100
        self.vis_bars = [0.0] * self.vis_count
        self.vis_offsets = [random.random() * 100 for _ in range(self.vis_count)]
        
        self.is_expanded = False
        self.is_hovered = False
        self.title_text = "Idle"
        self.artist_text = ""
        self.is_playing = False
        self.display_time = ""
        self.current_album_art = None
        self.last_img_bytes = b""
        
        # Progress Logic
        self.display_pos = 0.0 
        self.media_dur = 0.0
        self.last_tick_time = time.time()
        
        self.img_play = load_or_create_icon(IMG_PLAY_FILE, "play")
        self.img_pause = load_or_create_icon(IMG_PAUSE_FILE, "pause")
        self.img_next = load_or_create_icon(IMG_NEXT_FILE, "next")
        self.img_prev = load_or_create_icon(IMG_PREV_FILE, "prev")
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.game_loop)
        self.anim_timer.start(16) # 60 FPS
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_text)
        self.clock_timer.start(1000)
        
        self.worker = MediaWorker()
        self.worker.metadata_updated.connect(self.on_metadata_sync)
        self.worker.start()

        self.setup_tray()
        self.update_clock_text() 
        self.update_geometry()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(Qt.GlobalColor.black))
        p.drawEllipse(4, 4, 24, 24)
        p.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        menu = QMenu()
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_act)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def on_metadata_sync(self, title, artist, is_playing, remote_pos, dur, img_bytes):
        track_changed = (self.title_text != title)
        
        # [FIX] Update metadata
        self.title_text = title[:35] + "..." if len(title) > 35 else title
        self.artist_text = artist[:40] + "..." if len(artist) > 40 else artist
        self.media_dur = dur
        
        # Handle Art
        if img_bytes and img_bytes != self.last_img_bytes:
            self.last_img_bytes = img_bytes
            pix = QPixmap()
            if pix.loadFromData(img_bytes):
                self.current_album_art = pix
        elif not img_bytes:
            self.current_album_art = None
            self.last_img_bytes = b""
        
        # [FIX] Progress Sync Logic to prevent resets
        # 1. Calculate difference between local timer and windows timer
        diff = abs(remote_pos - self.display_pos)
        
        # 2. Check if Windows returned 0.0 erroneously (Common bug in WinRT)
        # If we are past 5 seconds, but remote says 0.0, it's likely a glitch.
        is_glitch_zero = (remote_pos == 0.0 and self.display_pos > 5.0)

        if track_changed:
            # New track? always take remote values
            self.display_pos = remote_pos
            self.is_playing = is_playing # Sync playing state
        elif not is_glitch_zero:
            # If drift is large (>5s), force sync
            # If we are paused, force sync (to correct seek positions)
            if diff > 5.0 or (not self.is_playing and diff > 0.5):
                self.display_pos = remote_pos
            
            # Only update play state if not recently clicked (handled by optimistic UI)
            # but generally we accept the remote state here
            self.is_playing = is_playing

        self.update()

    def update_clock_text(self):
        now = datetime.now()
        am_pm = now.strftime("%p").replace("AM", "A.M.").replace("PM", "P.M.")
        self.display_time = now.strftime(f"%I:%M - {am_pm}")

    def game_loop(self):
        # 1. Window Physics
        self.animate_spring()
        
        # 2. Button Physics
        for key, state in self.btn_anim.items():
            state['scale'] += (1.0 - state['scale']) * 0.2
            state['offset'] += (0.0 - state['offset']) * 0.2

        # 3. Visualizer Physics
        now_time = time.time()
        if self.is_playing:
            for i in range(self.vis_count):
                wave1 = math.sin(now_time * 5 + self.vis_offsets[i])
                wave2 = math.sin(now_time * 12 + self.vis_offsets[i] * 2)
                wave3 = math.sin(now_time * 2 + i * 0.1)
                raw_noise = (wave1 + wave2 + wave3 + 3) / 6
                val = math.pow(raw_noise, 2.5) 
                self.vis_bars[i] += (val - self.vis_bars[i]) * 0.3
        else:
            for i in range(self.vis_count):
                self.vis_bars[i] += (0.05 - self.vis_bars[i]) * 0.1
            
        # 4. Progress Timer
        dt = now_time - self.last_tick_time
        self.last_tick_time = now_time
        
        # [FIX] Prevent giant jumps if computer slept
        if dt > 1.0: 
            dt = 0.0

        if self.is_playing and self.media_dur > 0:
            self.display_pos += dt
            if self.display_pos > self.media_dur: 
                self.display_pos = self.media_dur
            self.update() 
        elif self.is_playing:
            # If duration is unknown, still allow update to trigger redraws
            self.update()

    def animate_spring(self):
        if self.is_expanded:
            self.target_w = EXPAND_W
            self.target_h = EXPAND_H
        elif self.is_hovered:
            self.target_w = HOVER_W
            self.target_h = HOVER_H
        else:
            self.target_w = IDLE_W
            self.target_h = IDLE_H

        force_w = (self.target_w - self.current_w) * SPRING_STIFFNESS
        force_h = (self.target_h - self.current_h) * SPRING_STIFFNESS
        
        self.vel_w += force_w
        self.vel_h += force_h
        
        self.vel_w *= SPRING_DAMPING
        self.vel_h *= SPRING_DAMPING
        
        self.current_w += self.vel_w
        self.current_h += self.vel_h
        
        if abs(self.vel_w) < 0.01 and abs(self.vel_h) < 0.01 and \
           abs(self.target_w - self.current_w) < 0.1 and abs(self.target_h - self.current_h) < 0.1:
             self.current_w = self.target_w
             self.current_h = self.target_h
        else:
            self.update_geometry()

    def update_geometry(self):
        w = int(self.current_w)
        h = int(self.current_h)
        x = (self.screen_width - w) // 2
        y = 0 
        self.setGeometry(x, y, w, h)

    def enterEvent(self, event):
        self.is_hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.is_expanded = False 
        super().leaveEvent(event)

    def format_time(self, seconds):
        if seconds < 0: return "0:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            
            if self.is_expanded and self.title_text != "Idle":
                w = self.width()
                h = self.height()
                pos = event.position()
                
                bar_y = h - BARYPOS
                btn_y = h - BTNYPOS
                
                # Seek Hit
                bar_x = 60
                bar_w = w - 120
                seek_rect = QRectF(bar_x, bar_y - 15, bar_w, 15)
                if seek_rect.contains(pos):
                    rel_x = pos.x() - bar_x
                    pct = max(0.0, min(1.0, rel_x / bar_w))
                    new_time = pct * self.media_dur
                    
                    # [FIX] Immediate seek update
                    self.display_pos = new_time
                    self.worker.seek_to(new_time)
                    self.update()
                    return

                # Button Hitbox
                center_x = w / 2
                btn_hit_size = 40
                
                prev_rect = QRectF(center_x - 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                play_rect = QRectF(center_x - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                next_rect = QRectF(center_x + 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                
                if play_rect.contains(pos):
                    # [FIX] Optimistic Update: Change state immediately
                    self.is_playing = not self.is_playing
                    self.btn_anim['play']['scale'] = 0.8
                    self.update() # Force repaint
                    self.worker.toggle_media()
                    return
                elif prev_rect.contains(pos):
                    self.worker.prev_track()
                    self.btn_anim['prev']['scale'] = 0.8
                    self.btn_anim['prev']['offset'] = -8.0
                    self.update() # Force repaint
                    return
                elif next_rect.contains(pos):
                    self.worker.next_track()
                    self.btn_anim['next']['scale'] = 0.8
                    self.btn_anim['next']['offset'] = 8.0 
                    self.update() # Force repaint
                    return
            
            self.is_expanded = not self.is_expanded
            self.vel_w += 10 if self.is_expanded else -5
            self.vel_h += 10 if self.is_expanded else -5

    def draw_animated_button(self, p, cx, cy, img, anim_key):
        state = self.btn_anim[anim_key]
        p.save()
        p.translate(cx + state['offset'], cy)
        p.scale(state['scale'], state['scale'])
        size = 40
        p.drawPixmap(-size//2, -size//2, img)
        p.restore()
        
    def draw_visualizer(self, p, x, y, h, width_available, color, align_bottom=False):
        p.save()
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        
        bar_w = 3
        gap = 2
        total_bar_width = bar_w + gap
        
        num_bars = int(width_available / total_bar_width)
        num_bars = min(num_bars, self.vis_count)
        
        for i in range(num_bars):
            val = self.vis_bars[i]
            bar_h = val * h
            
            bx = x + (i * total_bar_width)
            
            if align_bottom:
                p.drawRoundedRect(QRectF(bx, y - bar_h, bar_w, bar_h), 1.5, 1.5)
            else:
                p.drawRoundedRect(QRectF(bx, y - bar_h/2, bar_w, bar_h), 1.5, 1.5)
            
        p.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        w = self.width()
        h = self.height()
        path = QPainterPath()
        safe_radius = min(CORNER_RADIUS, h)
        
        path.moveTo(0, 0)
        path.lineTo(w, 0) 
        path.lineTo(w, h - safe_radius)
        path.cubicTo(w, h, w, h, w - safe_radius, h)
        path.lineTo(safe_radius, h) 
        path.cubicTo(0, h, 0, h, 0, h - safe_radius)
        path.lineTo(0, 0) 
        
        range_h = EXPAND_H - IDLE_H
        curr_off = self.current_h - IDLE_H
        progress = max(0.0, min(1.0, curr_off / range_h))
        
        # 1. Background
        if self.is_expanded and self.current_album_art and self.title_text != "Idle":
            p.save()
            p.setClipPath(path)
            p.setOpacity(progress) 
            
            img_w = self.current_album_art.width()
            img_h = self.current_album_art.height()
            scale_factor = h / img_h
            if (img_w * scale_factor) < w:
                scale_factor = w / img_w
            new_w = int(img_w * scale_factor)
            new_h = int(img_h * scale_factor)
            x_off = (w - new_w) / 2
            y_off = (h - new_h) / 2
            
            p.drawPixmap(int(x_off), int(y_off), new_w, new_h, self.current_album_art, 0, 0, img_w, img_h)
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, 80))
            
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))    
            grad.setColorAt(0.6, QColor(0, 0, 0, 180))
            grad.setColorAt(0.85, QColor(0, 0, 0, 255)) 
            grad.setColorAt(1.0, QColor(0, 0, 0, 255))
            p.fillRect(0, 0, w, h, grad)
            p.restore()
            
            if progress < 1.0:
                p.save()
                p.setOpacity(1.0 - progress)
                p.setBrush(QBrush(COLOR_BG))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path)
                p.restore()
        else:
            p.setBrush(QBrush(COLOR_BG))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
        
        vis_color = COLOR_ACCENT if self.is_playing else COLOR_PAUSED

        # 2. COLLAPSED CONTENT
        if progress < 0.8:
            p.save()
            opacity = 1.0 - (progress * 3) 
            p.setOpacity(max(0.0, opacity))
            center_y = h / 2
            
            if self.title_text != "Idle":
                if self.is_playing:
                    self.draw_visualizer(p, 20, center_y, 14, 25, vis_color, align_bottom=False)
                else:
                    dot_size = 6
                    p.setBrush(QBrush(vis_color))
                    p.drawEllipse(QPointF(25, center_y), dot_size/2, dot_size/2)
            
            if w > 120:
                p.setPen(QPen(COLOR_TEXT_MAIN))
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                offset_x = 45 if (self.is_playing and self.title_text != "Idle") else 30
                if self.title_text == "Idle": offset_x = 0
                text_rect = QRectF(offset_x, 0, w - offset_x, h)
                p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.display_time)
            p.restore()

        # 3. EXPANDED CONTENT
        if progress > 0.2:
            p.save()
            opacity = (progress - 0.2) / 0.8
            p.setOpacity(max(0.0, min(1.0, opacity)))

            if self.title_text == "Idle":
                p.setPen(QPen(COLOR_TEXT_MAIN))
                p.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.display_time)
                p.setPen(QPen(COLOR_TEXT_SUB))
                p.setFont(QFont("Segoe UI", 10))
                p.drawText(QRectF(0, 40, w, h), Qt.AlignmentFlag.AlignCenter, "No Media Playing")
            else:
                p.setPen(QPen(QColor(255, 255, 255, 150)))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                p.drawText(QRectF(0, 8, w, 20), Qt.AlignmentFlag.AlignCenter, self.display_time)

                p.setPen(QPen(COLOR_TEXT_MAIN))
                p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                p.drawText(QRectF(20, 30, w-40, 30), Qt.AlignmentFlag.AlignCenter, self.title_text)
                
                p.setPen(QPen(COLOR_TEXT_SUB))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QRectF(20, 55, w-40, 20), Qt.AlignmentFlag.AlignCenter, self.artist_text)

                bar_y = h - BARYPOS
                bar_x = 60
                bar_w = w - 120
                
                if self.is_playing:
                    self.draw_visualizer(p, bar_x, bar_y - 8, 25, bar_w, vis_color, align_bottom=True)
                
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(COLOR_BAR_BG))
                p.drawRoundedRect(QRectF(bar_x, bar_y - 8, bar_w, 4), 2, 2)
                
                if self.media_dur > 0:
                    prog_bar = min(1.0, max(0.0, self.display_pos / self.media_dur))
                    fill_w = bar_w * prog_bar
                    p.setBrush(QBrush(COLOR_TEXT_MAIN))
                    p.drawRoundedRect(QRectF(bar_x, bar_y - 8, fill_w, 4), 2, 2)
                    p.drawEllipse(QPointF(bar_x + fill_w, bar_y - 6), 4, 4)

                p.setPen(QPen(COLOR_TEXT_SUB))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                curr_time_str = self.format_time(self.display_pos)
                total_time_str = self.format_time(self.media_dur)
                p.drawText(20, bar_y, curr_time_str)
                p.drawText(w - 50, bar_y, total_time_str)

                center_x = w / 2
                btn_y = h - BTNYPOS
                self.draw_animated_button(p, center_x - 60, btn_y, self.img_prev, 'prev')
                if self.is_playing:
                    self.draw_animated_button(p, center_x, btn_y, self.img_pause, 'play')
                else:
                    self.draw_animated_button(p, center_x, btn_y, self.img_play, 'play')
                self.draw_animated_button(p, center_x + 60, btn_y, self.img_next, 'next')
            
            p.restore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = DynamicIsland()
    window.show()
    
    sys.exit(app.exec())