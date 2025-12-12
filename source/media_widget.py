import time
import math
import random
import os
from datetime import datetime

from PyQt6.QtWidgets import QMainWindow, QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QUrl, QMimeData, QPoint
from PyQt6.QtGui import (QPainter, QColor, QBrush, QFont, QPen, QAction, 
                         QIcon, QPixmap, QPainterPath, QLinearGradient, QFontMetrics, QDrag)

from config import *
from helpers import load_or_create_icon, format_time
from media_worker import MediaWorker

class DynamicIsland(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        self.screen_width = QApplication.primaryScreen().size().width()
        
        # Initialize state
        self._init_physics_state()
        self._init_button_state()
        self._init_visualizer_state()
        self._init_art_state()
        self._init_text_state()
        self._init_media_state()
        
        # Load icons
        self.img_play = load_or_create_icon(IMG_PLAY_FILE, "play")
        self.img_pause = load_or_create_icon(IMG_PAUSE_FILE, "pause")
        self.img_next = load_or_create_icon(IMG_NEXT_FILE, "next")
        self.img_prev = load_or_create_icon(IMG_PREV_FILE, "prev")
        
        # Load CD Image
        self.img_cd = QPixmap(IMG_CD_FILE)
        if self.img_cd.isNull():
            self.img_cd = QPixmap(200, 200)
            self.img_cd.fill(Qt.GlobalColor.transparent)
            p = QPainter(self.img_cd)
            p.setBrush(QBrush(QColor(30, 30, 30)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, 200, 200)
            p.end()
        
        # Setup timers
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.game_loop)
        self.anim_timer.start(16)  # 60 FPS
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_text)
        self.clock_timer.start(1000)
        
        # Setup media worker
        self.worker = MediaWorker()
        self.worker.metadata_updated.connect(self.on_metadata_sync)
        self.worker.start()

        self.update_clock_text() 
        self.update_geometry()

    def _init_physics_state(self):
        self.current_w = float(IDLE_W)
        self.current_h = float(IDLE_H)
        self.target_w = float(IDLE_W)
        self.target_h = float(IDLE_H)
        self.vel_w = 0.0
        self.vel_h = 0.0

    def _init_button_state(self):
        self.btn_anim = {
            'play': {'scale': 0.2, 'offset': 0.0},
            'prev': {'scale': 0.2, 'offset': 0.0},
            'next': {'scale': 0.2, 'offset': 0.0}
        }
        self.btn_hover_states = {'prev': False, 'play': False, 'next': False}
        self.btn_hover_anims = {'prev': 0.0, 'play': 0.0, 'next': 0.0}

    def _init_visualizer_state(self):
        self.vis_count = 100
        self.vis_bars = [0.0] * self.vis_count
        self.vis_offsets = [random.random() * 100 for _ in range(self.vis_count)]
        self.vis_multiplier = 0.0

    def _init_art_state(self):
        self.art_flip_progress = 0.0
        self.art_fade_progress = 0.0
        self.prev_album_art = None
        self.is_flipping_art = False
        self.is_fading_art = False
        self.art_is_square = True
        self.cd_rotation = 0.0
        self.box_fade_anim = 0.0 
        self.dominant_color = QColor(20, 20, 20)

    def _init_text_state(self):
        self.temp_mode_active = False
        self.temp_mode_start_time = 0.0
        self.temp_mode_progress = 0.0
        
        self.text_change_progress = 1.0 
        
        self.scroll_x = 0.0
        self.scroll_wait_timer = 0.0
        self.scroll_direction = 0
        self.text_fits = True
        self.title_text_width = 0.0
        self.available_text_w = 0.0
        
        self.idle_scale_anim = 1.0 

    def _init_media_state(self):
        self.bar_hover_anim = 0.0
        self.is_bar_hovered = False
        self.is_expanded = False
        self.is_hovered = False

        self.expand_progress = 0.0
        
        self.title_text = "Idle"
        self.raw_title = ""
        self.artist_text = ""
        self.is_playing = False
        self.display_time = ""
        
        self.current_album_art = None
        self.blurred_album_art = None 
        self.last_img_bytes = b""
        
        self.display_pos = 0.0
        self.media_dur = 0.0
        self.last_tick_time = time.time()

    def _generate_blurred_art(self, pixmap):
        if not pixmap or pixmap.isNull():
            return None
        small_pix = pixmap.scaled(64, 64, 
                                Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                Qt.TransformationMode.SmoothTransformation)
        target_size = max(self.screen_width, 1000) 
        blurred = small_pix.scaled(target_size, target_size, 
                                 Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                 Qt.TransformationMode.SmoothTransformation)
        return blurred

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
                
            self.text_change_progress = 0.0
            self.scroll_x = 0.0
            self.scroll_wait_timer = 5.0
            self.scroll_direction = 0
        
        if img_bytes and img_bytes != self.last_img_bytes:
            new_pix = QPixmap()
            if new_pix.loadFromData(img_bytes):
                self.prev_album_art = self.current_album_art
                self.current_album_art = new_pix
                self.last_img_bytes = img_bytes
                self.blurred_album_art = self._generate_blurred_art(new_pix)
                
                if new_pix.width() > 0 and new_pix.height() > 0:
                    ratio = new_pix.width() / new_pix.height()
                    self.art_is_square = (0.9 < ratio < 1.1)
                else:
                    self.art_is_square = True

                img = new_pix.toImage()
                cx, cy = img.width() // 2, img.height() // 2
                self.dominant_color = img.pixelColor(cx, cy)
                
                self.art_flip_progress = 0.0
                self.is_flipping_art = True
                self.art_fade_progress = 0.0
                self.is_fading_art = True
                self.box_fade_anim = 0.0
                
        elif not img_bytes and self.last_img_bytes:
            self.prev_album_art = self.current_album_art
            self.current_album_art = None
            self.blurred_album_art = None
            self.last_img_bytes = b""
            self.dominant_color = QColor(20, 20, 20)
            self.art_is_square = True
            
            self.art_flip_progress = 0.0
            self.is_flipping_art = True
            self.art_fade_progress = 0.0
            self.is_fading_art = True
            self.box_fade_anim = 0.0
        
        diff = abs(remote_pos - self.display_pos)
        is_glitch_zero = (remote_pos == 0.0 and self.display_pos > 5.0)

        if track_changed:
            self.display_pos = remote_pos
            self.is_playing = is_playing
        elif not is_glitch_zero:
            if diff > 5.0 or (not self.is_playing and diff > 0.5):
                self.display_pos = remote_pos
            self.is_playing = is_playing

        self.update()

    def update_clock_text(self):
        now = datetime.now()
        am_pm = now.strftime("%p").replace("AM", "A.M.").replace("PM", "P.M.")
        self.display_time = now.strftime(f"%I:%M - {am_pm}")

    def game_loop(self):
        self.animate_spring()
        btns_moving = self._animate_buttons()
        self._animate_album_art()

        now_time = time.time()
        dt = now_time - self.last_tick_time
        if dt > 1.0:
            dt = 0.0
        self.last_tick_time = now_time

        target_expand = 1.0 if self.is_expanded else 0.0
        self.expand_progress += (target_expand - self.expand_progress) * 0.1
        expand_animating = (abs(self.expand_progress - target_expand) > 0.001)

        text_animating = self._animate_temp_mode(now_time)
        
        self.text_change_progress += (1.0 - self.text_change_progress) * 0.1
        text_changing = (self.text_change_progress < 0.99)
        
        self.box_fade_anim += (1.0 - self.box_fade_anim) * 0.05
        box_fading = (self.box_fade_anim < 0.99)

        is_scrolling = self._animate_scroll(dt)
        self._animate_visualizer(now_time)
        
        target_bar = 1.0 if self.is_bar_hovered else 0.0
        self.bar_hover_anim += (target_bar - self.bar_hover_anim) * 0.2
        
        target_idle_scale = 1.0 if (self.title_text == "Idle") else 0.0
        self.idle_scale_anim += (target_idle_scale - self.idle_scale_anim) * 0.1
        idle_animating = (abs(self.idle_scale_anim - target_idle_scale) > 0.01)

        if self.is_playing:
            self.cd_rotation = (self.cd_rotation + 1.5) % 360
        
        if self.is_playing and self.media_dur > 0:
            self.display_pos += dt
            if self.display_pos > self.media_dur:
                self.display_pos = self.media_dur

        should_repaint = (
            self.is_playing or 
            self.vis_multiplier > 0.01 or 
            self.is_flipping_art or 
            self.is_fading_art or 
            btns_moving or 
            text_animating or
            text_changing or
            box_fading or
            self.temp_mode_active or
            abs(self.bar_hover_anim - target_bar) > 0.01 or
            is_scrolling or
            self.is_playing or
            idle_animating or
            expand_animating
        )
        
        if should_repaint:
            self.update()

    def _animate_buttons(self):
        btns_moving = False
        for key in ['prev', 'play', 'next']:
            target_hover = 1.0 if self.btn_hover_states[key] else 0.0
            self.btn_hover_anims[key] += (target_hover - self.btn_hover_anims[key]) * 0.2
            
            target_scale = 1.0 + (0.2 * self.btn_hover_anims[key])
            state = self.btn_anim[key]
            state['scale'] += (target_scale - state['scale']) * 0.2
            state['offset'] += (0.0 - state['offset']) * 0.2
            
            if (abs(state['scale'] - target_scale) > 0.001 or 
                abs(state['offset']) > 0.1 or 
                abs(self.btn_hover_anims[key] - target_hover) > 0.01):
                btns_moving = True
        return btns_moving

    def _animate_album_art(self):
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

    def _animate_temp_mode(self, now_time):
        if self.temp_mode_active:
            if now_time - self.temp_mode_start_time > TEMP_MODE_DURATION:
                self.temp_mode_active = False
            self.temp_mode_progress += (1.0 - self.temp_mode_progress) * 0.1
        else:
            self.temp_mode_progress += (0.0 - self.temp_mode_progress) * 0.1
        return (self.temp_mode_progress > 0.001 and self.temp_mode_progress < 0.999)

    def _animate_scroll(self, dt):
        should_scroll = (self.is_expanded or self.temp_mode_active) and not self.text_fits
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
                        if self.scroll_x <= 0: self.scroll_direction = 1
                        elif self.scroll_x >= max_scroll: self.scroll_direction = -1
                else:
                    if self.scroll_direction == 0: self.scroll_wait_timer = 5.0
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
        return is_scrolling

    def _animate_visualizer(self, now_time):
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

    def animate_spring(self):
        has_media = (self.title_text != "Idle")
        
        current_idle_w = MEDIA_IDLE_W + (MEDIA_TEMP_W - MEDIA_IDLE_W) * self.temp_mode_progress
        target_idle_w = current_idle_w if has_media else IDLE_W
        target_hover_w = MEDIA_HOVER_W if has_media else HOVER_W
        
        if self.is_expanded:
            self.target_w = EXPAND_W
            self.target_h = EXPAND_H
        elif self.is_hovered:
            self.target_w = target_hover_w
            self.target_h = HOVER_H
        else:
            self.target_w = target_idle_w
            self.target_h = IDLE_H

        force_w = (self.target_w - self.current_w) * SPRING_STIFFNESS
        force_h = (self.target_h - self.current_h) * SPRING_STIFFNESS
        self.vel_w += force_w
        self.vel_h += force_h
        self.vel_w *= SPRING_DAMPING
        self.vel_h *= SPRING_DAMPING
        self.current_w += self.vel_w
        self.current_h += self.vel_h
        
        if (abs(self.vel_w) < 0.01 and abs(self.vel_h) < 0.01 and 
            abs(self.target_w - self.current_w) < 0.1 and 
            abs(self.target_h - self.current_h) < 0.1):
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
            
    # --- Mouse Events ---
    def enterEvent(self, event):
        self.is_hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.is_expanded = False
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        w = self.width()
        h = self.height()
        
        # Removed tray interaction delegation

        # Media Controls Hover Logic 
        if self.is_expanded and self.title_text != "Idle":
            bar_y = h - BARYPOS
            bar_x = 220 
            bar_w = w - 240
            
            center_x = 220 + bar_w/2
            
            seek_rect = QRectF(bar_x, bar_y - 20, bar_w, 25)
            self.is_bar_hovered = seek_rect.contains(pos)
            
            btn_y = h - BTNYPOS
            btn_hit_size = 50
            
            self.btn_hover_states['prev'] = QRectF(center_x - 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
            self.btn_hover_states['play'] = QRectF(center_x - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
            self.btn_hover_states['next'] = QRectF(center_x + 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size).contains(pos)
        else:
            self.is_bar_hovered = False
            self.btn_hover_states = {'prev': False, 'play': False, 'next': False}
        
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            
            # Removed tray click handling

            w = self.width()
            h = self.height()
            
            # Media Interactions
            if self.is_expanded and self.title_text != "Idle":
                bar_y = h - BARYPOS
                btn_y = h - BTNYPOS
                bar_x = 220
                bar_w = w - 240
                center_x = 220 + bar_w/2
                
                seek_rect = QRectF(bar_x, bar_y - 15, bar_w, 15)
                if seek_rect.contains(pos):
                    rel_x = pos.x() - bar_x
                    pct = max(0.0, min(1.0, rel_x / bar_w))
                    new_time = pct * self.media_dur
                    self.display_pos = new_time
                    self.worker.seek_to(new_time)
                    self.update()
                    return

                btn_hit_size = 40
                prev_rect = QRectF(center_x - 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                play_rect = QRectF(center_x - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                next_rect = QRectF(center_x + 60 - btn_hit_size/2, btn_y - btn_hit_size/2, btn_hit_size, btn_hit_size)
                
                if play_rect.contains(pos):
                    self.is_playing = not self.is_playing
                    self.btn_anim['play']['scale'] = 0.8
                    self.update()
                    self.worker.toggle_media()
                    return
                elif prev_rect.contains(pos):
                    self.worker.prev_track()
                    self.btn_anim['prev']['scale'] = 0.8
                    self.btn_anim['prev']['offset'] = -8.0
                    self.update()
                    return
                elif next_rect.contains(pos):
                    self.worker.next_track()
                    self.btn_anim['next']['scale'] = 0.8
                    self.btn_anim['next']['offset'] = 8.0
                    self.update()
                    return
            
            # Global Toggle (Main Click)
            self.is_expanded = not self.is_expanded
            self.vel_w += 10 if self.is_expanded else -5
            self.vel_h += 10 if self.is_expanded else -5

    def paintEvent(self, event):
        from renderer import MediaRenderer
        renderer = MediaRenderer(self)
        renderer.render()