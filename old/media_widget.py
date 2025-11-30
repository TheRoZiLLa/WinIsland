import sys
import asyncio
import threading
import time
import os
import math
import random
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QBrush, QColor, QPainterPath, QLinearGradient, QFont, QPen, QFontMetrics

# WinRT Imports
from winrt.windows.media.control import \
    GlobalSystemMediaTransportControlsSessionManager, \
    GlobalSystemMediaTransportControlsSessionPlaybackStatus
    
try:
    from winrt.windows.storage.streams import DataReader
    HAS_STREAMS = True
except ImportError:
    HAS_STREAMS = False

# --- Configuration (Media Specific) ---
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

BARYPOS = 70
BTNYPOS = 40
TEMP_MODE_DURATION = 5.0

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

# --- Background Worker (Identical) ---
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

# --- Media Widget Logic ---
class MediaWidget(QObject):
    request_update = pyqtSignal()

    def __init__(self):
        super().__init__()
        
        # Core State
        self.title_text = "Idle"
        self.raw_title = ""
        self.artist_text = ""
        self.is_playing = False
        self.media_dur = 0.0
        self.display_pos = 0.0
        self.last_tick_time = time.time()
        
        # Button Animation State
        self.btn_anim = {
            'play': {'scale': 0.2, 'offset': 0.0},
            'prev': {'scale': 0.2, 'offset': 0.0},
            'next': {'scale': 0.2, 'offset': 0.0}
        }
        self.btn_hover_states = {'prev': False, 'play': False, 'next': False}
        self.btn_hover_anims = {'prev': 0.0, 'play': 0.0, 'next': 0.0}
        
        # Visualizer State
        self.vis_count = 100
        self.vis_bars = [0.0] * self.vis_count
        self.vis_offsets = [random.random() * 100 for _ in range(self.vis_count)]
        self.vis_multiplier = 0.0 
        
        # Album Art State
        self.current_album_art = None
        self.prev_album_art = None
        self.last_img_bytes = b""
        self.art_flip_progress = 0.0
        self.art_fade_progress = 0.0
        self.is_flipping_art = False
        self.is_fading_art = False
        
        # Temp Mode / Scrolling State
        self.temp_mode_active = False
        self.temp_mode_start_time = 0.0
        self.temp_mode_progress = 0.0 
        
        self.scroll_x = 0.0
        self.scroll_wait_timer = 0.0
        self.scroll_direction = 0
        self.text_fits = True
        self.title_text_width = 0.0
        self.available_text_w = 0.0
        
        # Progress Bar Hover
        self.bar_hover_anim = 0.0 
        self.is_bar_hovered = False
        
        # Assets
        self.img_play = load_or_create_icon(IMG_PLAY_FILE, "play")
        self.img_pause = load_or_create_icon(IMG_PAUSE_FILE, "pause")
        self.img_next = load_or_create_icon(IMG_NEXT_FILE, "next")
        self.img_prev = load_or_create_icon(IMG_PREV_FILE, "prev")
        
        # Worker
        self.worker = MediaWorker()
        self.worker.metadata_updated.connect(self.on_metadata_sync)
        self.worker.start()

    def on_metadata_sync(self, title, artist, is_playing, remote_pos, dur, img_bytes):
        track_changed = (self.raw_title != title)
        self.raw_title = title
        
        self.title_text = title 
        self.artist_text = artist[:40] + "..." if len(artist) > 40 else artist
        self.media_dur = dur
        
        if track_changed:
            if self.title_text == "Idle":
                self.temp_mode_active = False
            else:
                self.temp_mode_active = True
                self.temp_mode_start_time = time.time()
                
            # [RESET] Scroll State
            self.scroll_x = 0.0
            self.scroll_wait_timer = 5.0
            self.scroll_direction = 0
        
        # Handle Art
        if img_bytes and img_bytes != self.last_img_bytes:
            new_pix = QPixmap()
            if new_pix.loadFromData(img_bytes):
                self.prev_album_art = self.current_album_art
                self.current_album_art = new_pix
                self.last_img_bytes = img_bytes
                
                self.art_flip_progress = 0.0
                self.is_flipping_art = True
                self.art_fade_progress = 0.0
                self.is_fading_art = True
                
        elif not img_bytes and self.last_img_bytes:
            self.prev_album_art = self.current_album_art
            self.current_album_art = None
            self.last_img_bytes = b""
            self.art_flip_progress = 0.0
            self.is_flipping_art = True
            self.art_fade_progress = 0.0
            self.is_fading_art = True
        
        diff = abs(remote_pos - self.display_pos)
        is_glitch_zero = (remote_pos == 0.0 and self.display_pos > 5.0)

        if track_changed:
            self.display_pos = remote_pos
            self.is_playing = is_playing
        elif not is_glitch_zero:
            if diff > 5.0 or (not self.is_playing and diff > 0.5):
                self.display_pos = remote_pos
            self.is_playing = is_playing

        self.request_update.emit()

    def tick(self, is_expanded, is_window_hovered):
        """Called every 16ms, handles all physics"""
        now_time = time.time()
        dt = now_time - self.last_tick_time
        if dt > 1.0: dt = 0.0 
        self.last_tick_time = now_time
        
        # 1. Button Physics
        btns_moving = False
        for key in ['prev', 'play', 'next']:
            target_hover = 1.0 if self.btn_hover_states[key] else 0.0
            self.btn_hover_anims[key] += (target_hover - self.btn_hover_anims[key]) * 0.2
            
            target_scale = 1.0 + (0.2 * self.btn_hover_anims[key])
            state = self.btn_anim[key]
            state['scale'] += (target_scale - state['scale']) * 0.2
            state['offset'] += (0.0 - state['offset']) * 0.2
            
            if abs(state['scale'] - target_scale) > 0.001 or abs(state['offset']) > 0.1:
                btns_moving = True

        # 2. Art Animations
        if self.is_flipping_art:
            self.art_flip_progress += 0.05
            if self.art_flip_progress >= 1.0:
                self.art_flip_progress = 1.0
                self.is_flipping_art = False
        if self.is_fading_art:
            self.art_fade_progress += 0.04 
            if self.art_fade_progress >= 1.0:
                self.art_fade_progress = 1.0
                self.is_fading_art = False

        # 3. Temp Mode Animation
        if self.temp_mode_active:
            if now_time - self.temp_mode_start_time > TEMP_MODE_DURATION:
                self.temp_mode_active = False
            self.temp_mode_progress += (1.0 - self.temp_mode_progress) * 0.1
        else:
            self.temp_mode_progress += (0.0 - self.temp_mode_progress) * 0.1
        
        text_animating = (self.temp_mode_progress > 0.001 and self.temp_mode_progress < 0.999)

        # 4. Scroll Physics
        should_scroll = (is_expanded or self.temp_mode_active) and not self.text_fits
        is_scrolling = False
        if should_scroll:
            max_scroll = self.title_text_width - self.available_text_w
            if max_scroll < 0: max_scroll = 0
            
            if max_scroll > 0:
                speed = 30.0
                if self.scroll_wait_timer > 0:
                    self.scroll_wait_timer -= dt
                    if self.scroll_wait_timer <= 0:
                        self.scroll_wait_timer = 0
                        if self.scroll_x <= 0:
                            self.scroll_direction = 1 
                        elif self.scroll_x >= max_scroll:
                            self.scroll_direction = -1 
                else:
                    if self.scroll_direction == 0:
                        self.scroll_wait_timer = 5.0
                    elif self.scroll_direction == 1:
                        self.scroll_x += speed * dt
                        if self.scroll_x >= max_scroll:
                            self.scroll_x = max_scroll
                            self.scroll_direction = 0
                            self.scroll_wait_timer = 2.0
                    elif self.scroll_direction == -1:
                        self.scroll_x -= speed * dt
                        if self.scroll_x <= 0:
                            self.scroll_x = 0
                            self.scroll_direction = 0
                            self.scroll_wait_timer = 5.0
                    is_scrolling = True
        else:
            self.scroll_x = 0.0
            self.scroll_wait_timer = 0.0
            self.scroll_direction = 0

        # 5. Visualizer
        target_vis = 1.0 if self.is_playing else 0.0
        self.vis_multiplier += (target_vis - self.vis_multiplier) * 0.1
        for i in range(self.vis_count):
            if self.is_playing:
                wave1 = math.sin(now_time * 5 + self.vis_offsets[i])
                wave2 = math.sin(now_time * 12 + self.vis_offsets[i] * 2)
                wave3 = math.sin(now_time * 2 + i * 0.1)
                raw_noise = (wave1 + wave2 + wave3 + 3) / 6
                val = math.pow(raw_noise, 2.5) 
                self.vis_bars[i] += (val - self.vis_bars[i]) * 0.3
            else:
                self.vis_bars[i] += (0.05 - self.vis_bars[i]) * 0.1
        
        # 6. Progress Bar Hover
        target_bar = 1.0 if self.is_bar_hovered else 0.0
        self.bar_hover_anim += (target_bar - self.bar_hover_anim) * 0.2

        # 7. Media Time
        if self.is_playing and self.media_dur > 0:
            self.display_pos += dt
            if self.display_pos > self.media_dur: self.display_pos = self.media_dur
        
        # 8. Request Repaint
        should_repaint = (
            self.is_playing or 
            self.vis_multiplier > 0.01 or 
            self.is_flipping_art or 
            self.is_fading_art or 
            btns_moving or 
            text_animating or
            self.temp_mode_active or
            abs(self.bar_hover_anim - target_bar) > 0.01 or
            is_scrolling
        )
        if should_repaint:
            self.request_update.emit()

    def handle_mouse_move(self, pos, w, h, is_expanded):
        if is_expanded and self.title_text != "Idle":
            bar_y = h - BARYPOS
            bar_x = 60
            bar_w = w - 120
            
            seek_rect = QRectF(bar_x, bar_y - 20, bar_w, 25) 
            self.is_bar_hovered = seek_rect.contains(pos)
            
            center_x = w / 2
            btn_y = h - BTNYPOS
            btn_hit_size = 50
            
            self.btn_hover_states['prev'] = QRectF(center_x - 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
            self.btn_hover_states['play'] = QRectF(center_x - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
            self.btn_hover_states['next'] = QRectF(center_x + 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
        else:
            self.is_bar_hovered = False
            self.btn_hover_states = {'prev': False, 'play': False, 'next': False}

    def handle_mouse_press(self, pos, w, h):
        """Returns True if media logic handled the click"""
        if self.title_text != "Idle":
            bar_y = h - BARYPOS
            btn_y = h - BTNYPOS
            
            bar_x = 60
            bar_w = w - 120
            seek_rect = QRectF(bar_x, bar_y - 15, bar_w, 15)
            if seek_rect.contains(pos):
                rel_x = pos.x() - bar_x
                pct = max(0.0, min(1.0, rel_x / bar_w))
                new_time = pct * self.media_dur
                self.display_pos = new_time
                self.worker.seek_to(new_time)
                self.request_update.emit()
                return True

            center_x = w / 2
            btn_hit_size = 40
            
            prev_rect = QRectF(center_x - 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
            play_rect = QRectF(center_x - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
            next_rect = QRectF(center_x + 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
            
            if play_rect.contains(pos):
                self.is_playing = not self.is_playing
                self.btn_anim['play']['scale'] = 0.8
                self.worker.toggle_media()
                self.request_update.emit()
                return True
            elif prev_rect.contains(pos):
                self.worker.prev_track()
                self.btn_anim['prev']['scale'] = 0.8
                self.btn_anim['prev']['offset'] = -8.0
                self.request_update.emit()
                return True
            elif next_rect.contains(pos):
                self.worker.next_track()
                self.btn_anim['next']['scale'] = 0.8
                self.btn_anim['next']['offset'] = 8.0 
                self.request_update.emit()
                return True
        return False

    def paint_expanded_content(self, p, w, h, opacity, display_time):
        if self.title_text == "Idle":
            p.setPen(QPen(COLOR_TEXT_MAIN))
            p.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, display_time)
            p.setPen(QPen(COLOR_TEXT_SUB))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(QRectF(0, 40, w, h), Qt.AlignmentFlag.AlignCenter, "No Media Playing")
        else:
            p.setPen(QPen(QColor(255, 255, 255, 150)))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(0, 8, w, 20), Qt.AlignmentFlag.AlignCenter, display_time)

            # Title with Scrolling
            text_rect = QRectF(20, 30, w - 40, 30)
            self._draw_scrolling_text(p, text_rect, self.title_text, QFont("Segoe UI", 13, QFont.Weight.Bold), COLOR_TEXT_MAIN)
            
            p.setPen(QPen(COLOR_TEXT_SUB))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(20, 55, w-40, 20), Qt.AlignmentFlag.AlignCenter, self.artist_text)

            bar_y = h - BARYPOS
            bar_x = 60
            bar_w = w - 120
            
            if self.vis_multiplier > 0.01:
                progress_ratio = self.display_pos / self.media_dur if self.media_dur > 0 else 0
                self._draw_visualizer(p, bar_x, bar_y - 8, 25, bar_w, progress_ratio, bar_width=5, align_bottom=True)
            
            # Animated Progress Bar
            anim_height = 4.0 + (4.0 * self.bar_hover_anim) # 4px -> 8px
            anim_radius = anim_height / 2.0
            draw_y = (bar_y - 6) - (anim_height / 2.0)
            
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(COLOR_BAR_BG))
            p.drawRoundedRect(QRectF(bar_x, draw_y, bar_w, anim_height), anim_radius, anim_radius)
            
            if self.media_dur > 0:
                prog_bar = min(1.0, max(0.0, self.display_pos / self.media_dur))
                fill_w = bar_w * prog_bar
                p.setBrush(QBrush(COLOR_TEXT_MAIN))
                p.drawRoundedRect(QRectF(bar_x, draw_y, fill_w, anim_height), anim_radius, anim_radius)
                
                handle_radius = 4.0 + (1.0 * self.bar_hover_anim) # 4px -> 5px radius
                p.drawEllipse(QPointF(bar_x + fill_w, bar_y - 6), handle_radius, handle_radius)

            p.setPen(QPen(COLOR_TEXT_SUB))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            curr_time_str = self._format_time(self.display_pos)
            total_time_str = self._format_time(self.media_dur)
            p.drawText(20, bar_y, curr_time_str)
            p.drawText(w - 50, bar_y, total_time_str)

            center_x = w / 2
            btn_y = h - BTNYPOS
            self._draw_anim_btn(p, center_x - 60, btn_y, self.img_prev, 'prev')
            if self.is_playing:
                self._draw_anim_btn(p, center_x, btn_y, self.img_pause, 'play')
            else:
                self._draw_anim_btn(p, center_x, btn_y, self.img_play, 'play')
            self._draw_anim_btn(p, center_x + 60, btn_y, self.img_next, 'next')

    def paint_collapsed_content(self, p, w, h, opacity, display_time):
        center_y = h / 2
        
        # Center Text Area
        if w > 120:
            t_val = self.temp_mode_progress 
            
            # Time
            if t_val < 0.99:
                p.save()
                time_opacity = 1.0 - t_val
                time_scale = 1.0 - (0.3 * t_val) 
                p.setOpacity(max(0.0, time_opacity * opacity))
                p.translate(w/2, h/2)
                p.scale(time_scale, time_scale)
                p.translate(-w/2, -h/2)
                p.setPen(QPen(COLOR_TEXT_MAIN))
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, display_time)
                p.restore()
            
            # Title (Scrolling)
            if t_val > 0.01:
                p.save()
                title_opacity = t_val
                title_scale = 0.7 + (0.3 * t_val)
                p.setOpacity(max(0.0, title_opacity * opacity))
                p.translate(w/2, h/2)
                p.scale(title_scale, title_scale)
                p.translate(-w/2, -h/2)
                
                title_rect = QRectF(45, 0, w-90, h)
                self._draw_scrolling_text(p, title_rect, self.title_text, QFont("Segoe UI", 10, QFont.Weight.Bold), COLOR_TEXT_MAIN)
                p.restore()

        if self.title_text != "Idle":
            # Album Art (Left)
            art_size = 24
            art_x = 15
            art_y = int(center_y - art_size/2)
            
            p.save()
            draw_pix = self.current_album_art
            scale_anim_x = 1.0
            scale_anim_y = 1.0
            
            if self.is_flipping_art:
                center_art_x = art_x + art_size/2
                center_art_y = art_y + art_size/2
                p.translate(center_art_x, center_art_y)
                if self.art_flip_progress < 0.5:
                    draw_pix = self.prev_album_art
                    scale_anim_x = 1.0 - (self.art_flip_progress * 2)
                    scale_anim_y = 1.0 - (self.art_flip_progress * 0.6) 
                else:
                    draw_pix = self.current_album_art
                    scale_anim_x = (self.art_flip_progress - 0.5) * 2
                    scale_anim_y = 0.7 + ((self.art_flip_progress - 0.5) * 0.6)
                p.scale(scale_anim_x, scale_anim_y) 
                p.translate(-center_art_x, -center_art_y)
            
            if draw_pix:
                art_path = QPainterPath()
                art_path.addRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
                p.setClipPath(art_path)
                p.drawPixmap(art_x, art_y, art_size, art_size, draw_pix)
            else:
                p.setBrush(QBrush(QColor(40, 40, 40)))
                p.drawRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
            p.restore()

            # Visualizer (Right)
            vis_w = 30
            vis_x = w - vis_w - 15
            
            if self.vis_multiplier > 0.01:
                progress_ratio = self.display_pos / self.media_dur if self.media_dur > 0 else 0
                self._draw_visualizer(p, vis_x, center_y, 14, vis_w, progress_ratio, bar_width=3, align_bottom=False)
            else:
                dot_size = 6
                p.setBrush(QBrush(COLOR_ACCENT))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(vis_x + vis_w/2, center_y), dot_size/2, dot_size/2)

    def paint_background_art(self, p, w, h, clip_path, opacity_mult):
        show_bg = self.title_text != "Idle" and (self.current_album_art or (self.is_fading_art and self.prev_album_art))
        
        if show_bg:
            p.save()
            p.setClipPath(clip_path)
            
            def draw_cover(pix, opacity):
                if not pix: return
                p.save()
                p.setOpacity(opacity_mult * opacity)
                img_w = pix.width()
                img_h = pix.height()
                scale_factor = h / img_h
                if (img_w * scale_factor) < w:
                    scale_factor = w / img_w
                new_w = int(img_w * scale_factor)
                new_h = int(img_h * scale_factor)
                x_off = (w - new_w) / 2
                y_off = (h - new_h) / 2
                p.drawPixmap(int(x_off), int(y_off), new_w, new_h, pix, 0, 0, img_w, img_h)
                p.restore()

            if self.is_fading_art and self.prev_album_art:
                draw_cover(self.prev_album_art, 1.0)
                draw_cover(self.current_album_art, self.art_fade_progress)
            else:
                draw_cover(self.current_album_art, 1.0)

            p.setOpacity(opacity_mult)
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, 80))
            
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))    
            grad.setColorAt(0.6, QColor(0, 0, 0, 180))
            grad.setColorAt(0.85, QColor(0, 0, 0, 255)) 
            grad.setColorAt(1.0, QColor(0, 0, 0, 255))
            p.fillRect(0, 0, w, h, grad)
            p.restore()
            return True # Drew art
        return False # Did not draw art

    def _draw_visualizer(self, p, x, y, h, width_available, progress_ratio, bar_width, align_bottom):
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        gap = 2
        total_bar_width = bar_width + gap
        num_bars = int(width_available / total_bar_width)
        num_bars = min(num_bars, self.vis_count)
        c_played = COLOR_ACCENT
        c_upcoming = COLOR_BAR_BG 
        
        for i in range(num_bars):
            val = self.vis_bars[i]
            bar_h = val * h * self.vis_multiplier
            bar_pos_ratio = i / max(1, num_bars)
            if bar_pos_ratio < progress_ratio:
                p.setBrush(QBrush(c_played))
            else:
                p.setBrush(QBrush(c_upcoming))
            bx = x + (i * total_bar_width)
            if align_bottom:
                p.drawRoundedRect(QRectF(bx, y - bar_h, bar_width, bar_h), 1.5, 1.5)
            else:
                p.drawRoundedRect(QRectF(bx, y - bar_h/2, bar_width, bar_h), 1.5, 1.5)
        p.restore()

    def _draw_scrolling_text(self, p, rect, text, font, color):
        p.save()
        p.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        available_w = rect.width()
        
        # Sync metrics to logic
        self.title_text_width = text_w
        self.available_text_w = available_w
        self.text_fits = (text_w <= available_w)
        
        p.setClipRect(rect)
        if self.text_fits:
            p.setPen(QPen(color))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        else:
            grad = QLinearGradient(rect.topLeft(), rect.topRight())
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 0))
            grad.setColorAt(0.1, color)
            grad.setColorAt(0.9, color)
            grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(QPen(QBrush(grad), 0))
            draw_x = rect.x() - self.scroll_x
            draw_rect = QRectF(draw_x, rect.y(), text_w + 50, rect.height())
            p.drawText(draw_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()

    def _draw_anim_btn(self, p, cx, cy, img, anim_key):
        state = self.btn_anim[anim_key]
        p.save()
        p.translate(cx + state['offset'], cy)
        p.scale(state['scale'], state['scale'])
        size = 40
        p.drawPixmap(-size//2, -size//2, img)
        p.restore()

    def _format_time(self, seconds):
        if seconds < 0: return "0:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"