from PyQt6.QtCore import Qt, QRectF, QPointF, QFileInfo
from PyQt6.QtGui import (QPainter, QBrush, QPen, QFont, QPainterPath, 
                         QLinearGradient, QColor, QFontMetrics, QPixmap, QIcon)
from PyQt6.QtWidgets import QFileIconProvider
import math
import time

from config import *
from helpers import format_time

class MediaRenderer:
    def __init__(self, widget):
        self.widget = widget
        self.painter = QPainter(widget)
        self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        self.w = widget.width()
        self.h = widget.height()
        
    def render(self):
        self.progress = self.widget.expand_progress
        
        self.progress_ratio = 0.0
        if self.widget.media_dur > 0:
            self.progress_ratio = self.widget.display_pos / self.widget.media_dur
        
        self.clip_path = self._create_clip_path()
        
        self._render_background()
        
        if self.widget.title_text != "Idle":
            self._render_interpolating_album_art()
        
        self._render_collapsed_content()
        self._render_expanded_content()
        
        self.painter.end()
    
    def _create_clip_path(self):
        """Creates the clip path for the MAIN island content."""
        path = QPainterPath()
        safe_radius = min(CORNER_RADIUS, self.h)
        
        # Simple Pill Shape (No bubble offset)
        path.moveTo(0, 0)
        path.lineTo(self.w, 0)
        path.lineTo(self.w, self.h - safe_radius)
        path.cubicTo(self.w, self.h, self.w, self.h, self.w - safe_radius, self.h)
        path.lineTo(safe_radius, self.h)
        path.cubicTo(0, self.h, 0, self.h, 0, self.h - safe_radius)
        path.lineTo(0, 0)
            
        return path
    
    def _render_background(self):
        show_expanded_bg = self.widget.is_expanded
        
        if show_expanded_bg:
            self.painter.save()
            self.painter.setClipPath(self.clip_path)
            # self.painter.setOpacity(self.progress)
            
            has_media_art = self.widget.title_text != "Idle" and self.widget.current_album_art

            if has_media_art:
                # 1. Background Album Art Layer
                bg_pix = self.widget.blurred_album_art if self.widget.blurred_album_art else self.widget.current_album_art
                
                if bg_pix and not bg_pix.isNull():
                    scaled_bg = bg_pix.scaled(self.w, self.h, 
                                            Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                            Qt.TransformationMode.SmoothTransformation)
                    
                    x = (self.w - scaled_bg.width()) // 2
                    y = (self.h - scaled_bg.height()) // 2
                    self.painter.drawPixmap(x, y, scaled_bg)

                # 2. Gradient Overlay Layer
                img = self.widget.current_album_art.toImage()
                w, h = img.width(), img.height()
                
                c1 = img.pixelColor(w // 2, h // 2)         # Center
                c2 = img.pixelColor(w // 4, h // 4)         # Top-Left Quadrant
                c3 = img.pixelColor(3 * w // 4, 3 * h // 4) # Bottom-Right Quadrant
                
                t = time.time()
                t_rot = t * 0.4
                t_move = t * 0.6

                cx, cy = self.w / 2, self.h / 2
                radius = max(self.w, self.h) * 1.5 
                
                x1 = cx + math.cos(t_rot) * radius
                y1 = cy + math.sin(t_rot) * radius
                x2 = cx - math.cos(t_rot) * radius
                y2 = cy - math.sin(t_rot) * radius
                
                grad = QLinearGradient(x1, y1, x2, y2)
                
                alpha = 180
                c1.setAlpha(alpha)
                c2.setAlpha(alpha)
                c3.setAlpha(alpha)

                mid_pos = 0.5 + 0.25 * math.sin(t_move)

                grad.setColorAt(0.0, c2)
                grad.setColorAt(mid_pos, c1)
                grad.setColorAt(1.0, c3)
                
                self.painter.fillRect(0, 0, self.w, self.h, grad)
                
                # 3. Darkening Layer
                self.painter.fillRect(0, 0, self.w, self.h, QColor(0, 0, 0, 40))
                
                # Stronger bottom gradient for controls
                grad_black = QLinearGradient(0, 0, 0, self.h)
                grad_black.setColorAt(0.0, QColor(0, 0, 0, 0))
                grad_black.setColorAt(0.2, QColor(0, 0, 0, 40))
                grad_black.setColorAt(0.5, QColor(0, 0, 0, 180))
                grad_black.setColorAt(0.8, QColor(0, 0, 0, 220))
                grad_black.setColorAt(1.0, QColor(0, 0, 0, 255))
                
                self.painter.fillRect(0, 0, self.w, self.h, grad_black)
            else:
                self.painter.setBrush(QBrush(QColor(20, 20, 20)))
                self.painter.drawRect(0, 0, self.w, self.h)

            self.painter.restore()
            
            if self.progress < 1.0:
                self.painter.save()
                self.painter.setOpacity(1.0 - self.progress)
                self.painter.setBrush(QBrush(COLOR_BG))
                self.painter.setPen(Qt.PenStyle.NoPen)
                self.painter.drawPath(self.clip_path)
                self.painter.restore()
        else:
            self.painter.setBrush(QBrush(COLOR_BG))
            self.painter.setPen(Qt.PenStyle.NoPen)
            self.painter.drawPath(self.clip_path)

    def _render_interpolating_album_art(self):
        if not self.widget.current_album_art:
            return

        start_size = 24
        start_x = 15
        start_y = (IDLE_H - start_size) / 2
        
        max_box_h = 130
        max_box_w = 180 
        
        scaled_pix = self.widget.current_album_art.scaled(
            int(max_box_w), int(max_box_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        end_w = scaled_pix.width()
        end_h = scaled_pix.height()
        end_x = 25
        end_y = (self.h - end_h) // 2 - 10
        
        t = self.progress
        t = t * t * (3 - 2 * t)
        
        curr_w = start_size + (end_w - start_size) * t
        curr_h = start_size + (end_h - start_size) * t
        curr_x = start_x + (end_x - start_x) * t
        curr_y = start_y + (end_y - start_y) * t
        
        self.painter.save()
        
        if self.progress > 0.1:
            cd_opacity = (self.progress - 0.1) / 0.9
            self.painter.setOpacity(cd_opacity * self.widget.text_change_progress)
            
            cd_size = 140
            target_cd_x = end_x + CD_OFFSET_X
            curr_cd_x = curr_x + (target_cd_x - end_x) * t
            cd_y_pos = (self.h - cd_size) // 2 - 10
            
            center_x = curr_cd_x + cd_size/2
            center_y = cd_y_pos + cd_size/2
            
            self.painter.save()
            self.painter.translate(center_x, center_y)
            self.painter.rotate(self.widget.cd_rotation)
            self.painter.translate(-center_x, -center_y)
            
            if self.widget.img_cd:
                self.painter.drawPixmap(int(curr_cd_x), int(cd_y_pos), int(cd_size), int(cd_size), self.widget.img_cd)
            
            art_diam = int(cd_size * 0.4)
            art_x = center_x - art_diam/2
            art_y = center_y - art_diam/2
            path = QPainterPath()
            path.addEllipse(QRectF(art_x, art_y, art_diam, art_diam))
            self.painter.setClipPath(path)
            self.painter.drawPixmap(int(art_x), int(art_y), art_diam, art_diam, self.widget.current_album_art)
            self.painter.restore()

        box_opacity = 1.0
        if self.progress > 0.8:
             box_opacity = self.widget.box_fade_anim
        self.painter.setOpacity(box_opacity)

        if self.progress > 0.2:
            self.painter.setPen(Qt.PenStyle.NoPen)
            shadow_alpha = int(100 * self.progress)
            self.painter.setBrush(QBrush(QColor(0, 0, 0, shadow_alpha)))
            self.painter.drawRoundedRect(QRectF(curr_x+4*t, curr_y+4*t, curr_w, curr_h), 4, 4)

        path = QPainterPath()
        path.addRoundedRect(QRectF(curr_x, curr_y, curr_w, curr_h), 4, 4)
        self.painter.setClipPath(path)
        self.painter.drawPixmap(QRectF(curr_x, curr_y, curr_w, curr_h).toRect(), 
                               self.widget.current_album_art)
        
        if self.progress > 0.5:
            grad = QLinearGradient(curr_x, curr_y, curr_x + curr_w, curr_y + curr_h)
            gloss_alpha = int(30 * self.progress)
            grad.setColorAt(0.0, QColor(255, 255, 255, gloss_alpha))
            grad.setColorAt(0.5, QColor(255, 255, 255, 0))
            self.painter.fillRect(QRectF(curr_x, curr_y, curr_w, curr_h), grad)

        self.painter.restore()

    def _render_collapsed_content(self):
        if self.progress >= 0.8:
            return
            
        self.painter.save()
        opacity = 1.0 - (self.progress * 3)
        self.painter.setOpacity(max(0.0, opacity))
        
        center_x = self.w / 2
        center_y = self.h / 2
        
        if self.w > 120:
            anim_progress = self.widget.temp_mode_progress 
            
            if anim_progress < 0.99:
                self.painter.save()
                time_scale = 0.6 + (0.4 * (1.0 - anim_progress))
                time_opacity = 1.0 - anim_progress
                
                self.painter.translate(center_x, center_y)
                self.painter.scale(time_scale, time_scale)
                self.painter.translate(-center_x, -center_y)
                self.painter.setOpacity(max(0.0, opacity * time_opacity))
                
                self.painter.setPen(QPen(COLOR_TEXT_MAIN))
                self.painter.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
                
                self.painter.drawText(QRectF(0, 0, self.w, self.h), 
                                     Qt.AlignmentFlag.AlignCenter, 
                                     self.widget.display_time)
                self.painter.restore()
            
            if anim_progress > 0.01:
                self.painter.save()
                title_scale = 0.6 + (0.4 * anim_progress)
                title_opacity = anim_progress
                
                self.painter.translate(center_x, center_y)
                self.painter.scale(title_scale, title_scale)
                self.painter.translate(-center_x, -center_y)
                self.painter.setOpacity(max(0.0, opacity * title_opacity))
                
                title_rect = QRectF(45, 0, self.w - 90, self.h)
                self._draw_scrolling_text(title_rect, self.widget.title_text, 
                                         QFont(FONT_FAMILY, 10, QFont.Weight.Bold), 
                                         COLOR_TEXT_MAIN)
                self.painter.restore()

        if self.widget.title_text != "Idle":
            vis_w = 30
            vis_x = self.w - vis_w - 15
                
            if self.widget.vis_multiplier > 0.01:
                # Use Bar Visualizer for Collapsed Mode
                self._draw_visualizer(vis_x, center_y, 14, vis_w, self.progress_ratio, 
                                     bar_width=3, align_bottom=False)
            else:
                dot_size = 6
                self.painter.setBrush(QBrush(COLOR_ACCENT))
                self.painter.setPen(Qt.PenStyle.NoPen)
                self.painter.drawEllipse(QPointF(vis_x + vis_w/2, center_y), dot_size/2, dot_size/2)
        
        self.painter.restore()
    
    def _render_expanded_content(self):
        if self.progress <= 0.2:
            return
            
        self.painter.save()
        opacity = (self.progress - 0.2) / 0.8
        self.painter.setOpacity(max(0.0, min(1.0, opacity)))

        if self.widget.title_text == "Idle":
            self._render_idle_state()
        else:
            self._render_cd_layout_controls_only(self.w)
        
        self.painter.restore()

    def _render_idle_state(self):
        scale = 0.8 + (0.2 * self.widget.idle_scale_anim)
        opacity = self.widget.idle_scale_anim
        
        self.painter.save()
        cx, cy = self.w / 2, self.h / 2
        self.painter.translate(cx, cy)
        self.painter.scale(scale, scale)
        self.painter.translate(-cx, -cy)
        self.painter.setOpacity(opacity)
        
        self.painter.setPen(QPen(COLOR_TEXT_MAIN))
        self.painter.setFont(QFont(FONT_FAMILY, FONT_SIZE_CLOCK, QFont.Weight.Bold))
        self.painter.drawText(QRectF(0, 0, self.w, self.h), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.display_time)
        
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont(FONT_FAMILY, 10))
        self.painter.drawText(QRectF(0, 40, self.w, self.h), 
                             Qt.AlignmentFlag.AlignCenter, 
                             "No Media Playing")
        self.painter.restore()
    
    def _render_cd_layout_controls_only(self, width):
        content_x = 220
        content_w = width - content_x - 20
        
        text_scale = 1.0 + (0.2 * self.widget.text_change_progress)
        text_opacity = self.widget.text_change_progress
        
        self.painter.save()
        cx_text = content_x + content_w / 2
        cy_text = 45 
        self.painter.translate(cx_text, cy_text)
        self.painter.scale(text_scale, text_scale)
        self.painter.translate(-cx_text, -cy_text)
        self.painter.setOpacity(text_opacity)

        text_rect = QRectF(content_x + 30, 30, content_w - 40, 30)
        self._draw_scrolling_text(text_rect, self.widget.title_text, 
                                 QFont(FONT_FAMILY, FONT_SIZE_TITLE, QFont.Weight.Bold), 
                                 COLOR_TEXT_MAIN)
        
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont(FONT_FAMILY, FONT_SIZE_ARTIST))
        self.painter.drawText(QRectF(content_x + 10, 55, content_w, 20), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.artist_text)
        self.painter.restore()

        self._render_progress_bar_cd_style(content_x, content_w)
        self._render_control_buttons_cd_style(content_x, content_w)

    def _render_progress_bar_cd_style(self, x, w):
        bar_y = self.h - BARYPOS
        
        track_h = 6
        track_y = bar_y - track_h/2

        height = 8.0
        radius = height / 2.0
        draw_y = (bar_y - 6) - (height / 2.0)
        
        base_color = self.widget.dominant_color
        if not base_color.isValid():
            base_color = COLOR_BAR_BG
        else:
            base_color = QColor(base_color)
            base_color.setAlpha(50)

        base_color2 = self.widget.dominant_color
        if not base_color2.isValid():
            base_color2 = COLOR_TEXT_MAIN
        else:
            base_color2 = QColor(base_color2)

        self.painter.setPen(Qt.PenStyle.NoPen)
        self.painter.setBrush(QBrush(base_color))
        self.painter.drawRoundedRect(QRectF(x, track_y - 6, w, track_h), track_h/2, track_h/2)
        
        if self.widget.media_dur > 0:
            self._draw_samsung_wave_progress(x, bar_y, w, self.progress_ratio)

            prog_bar = min(1.0, max(0.0, self.widget.display_pos / self.widget.media_dur))
            fill_w = w * prog_bar
            self.painter.setBrush(QBrush(base_color2))
            self.painter.drawRoundedRect(QRectF(x - 2, draw_y, fill_w, height), 
                                        radius, radius)
            
            handle_radius = 7.0 + (1.0 * self.widget.bar_hover_anim)
            self.painter.setBrush(QBrush(Qt.GlobalColor.white))
            self.painter.drawEllipse(QPointF(x + fill_w, bar_y - 6), 
                                        handle_radius, handle_radius)

        # 3. Time Text
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont(FONT_FAMILY, FONT_SIZE_TIME, QFont.Weight.Bold))
        curr_time_str = format_time(self.widget.display_pos)
        total_time_str = format_time(self.widget.media_dur)
        self.painter.drawText(int(x), int(bar_y + 15), curr_time_str)
        self.painter.drawText(int(x + w - 30), int(bar_y + 15), total_time_str)

    def _draw_samsung_wave_progress(self, start_x, center_y, full_width, pct):
        pct = max(0.0, min(1.0, pct))
        fill_w = full_width * pct
        
        if fill_w < 1:
            return

        self.painter.save()
        self.painter.setPen(Qt.PenStyle.NoPen)

        # 1. Get Color from Album Art
        base_color = self.widget.dominant_color
        if not base_color.isValid():
            base_color = QColor("#56CCF2")

        c1 = base_color
        c2 = base_color.lighter(130) # Slightly lighter end for gradient
        
        grad = QLinearGradient(start_x, center_y, start_x + fill_w, center_y)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        
        # 2. Audio Reactivity
        avg_intensity = 0.0
        if self.widget.vis_count > 5:
            for i in range(5):
                avg_intensity += self.widget.vis_bars[i]
            avg_intensity /= 5.0
        
        # 3. Draw 3 Layers of Waves
        # Order: Back (0.3) -> Middle (0.5) -> Front (0.7)
        # Shift Y up by 6 pixels
        draw_y = center_y - 10
        
        t = time.time()
        base_amp = 3.0 + (avg_intensity * 10.0 * self.widget.vis_multiplier)
        freq = 0.05
        
        layers = [
            {'alpha': 0.25, 'speed': 5.0, 'phase': 3.0, 'amp_mult': 1.2},
            {'alpha': 0.5, 'speed': 6.0, 'phase': 2.5, 'amp_mult': 1.2},
            {'alpha': 0.75, 'speed': 7.0, 'phase': 1.5, 'amp_mult': 1.1},
            {'alpha': 1.0, 'speed': 8.0, 'phase': 0.0, 'amp_mult': 1.0}
        ]

        for layer in layers:
            self.painter.setOpacity(layer['alpha'])
            
            # Construct Wave Path
            path = QPainterPath()
            # Bottom of the wave shape (also shifted up)
            path.moveTo(start_x, draw_y + 6) 
            
            steps = int(fill_w / 2)
            if steps < 2: steps = 2
            
            speed = layer['speed']
            phase = layer['phase']
            amp = base_amp * layer['amp_mult']

            for i in range(steps + 1):
                px = start_x + (i * 2)
                if px > start_x + fill_w: px = start_x + fill_w
                
                # Dampening calculations to smooth ends to 0
                dist_from_start = px - start_x
                dist_from_end = (start_x + fill_w) - px
                taper_len = 60.0 # Pixel range for tapering
                
                damp_start = min(1.0, dist_from_start / taper_len)
                damp_end = min(1.0, dist_from_end / taper_len)
                dampening = damp_start * damp_end

                # Sine wave calculation
                # Original center was (center_y - 2). Shifting up by 6 makes it (draw_y - 2).
                wave_y = draw_y - (math.sin(px * freq - t * speed + phase) * amp * dampening)
                path.lineTo(px, wave_y)
                
            path.lineTo(start_x + fill_w, draw_y + 6) # Bottom right
            path.lineTo(start_x, draw_y + 6)          # Close loop
            
            self.painter.setBrush(QBrush(grad))
            self.painter.drawPath(path)

        # # 4. Draw Handle (on top of everything)
        # self.painter.setOpacity(1.0)
        # handle_x = start_x + fill_w
        # handle_radius = 7.0 + (2.0 * avg_intensity * self.widget.vis_multiplier)
        # self.painter.setBrush(QBrush(Qt.GlobalColor.white))
        # self.painter.drawEllipse(QPointF(handle_x, draw_y + 4), handle_radius, handle_radius)
        
        self.painter.restore()

    def _render_control_buttons_cd_style(self, x, w):
        center_x = x + w/2
        btn_y = self.h - BTNYPOS
        
        self._draw_animated_button(center_x - 60, btn_y, 
                                   self.widget.img_prev, 'prev')
        
        if self.widget.is_playing:
            self._draw_animated_button(center_x, btn_y, 
                                       self.widget.img_pause, 'play')
        else:
            self._draw_animated_button(center_x, btn_y, 
                                       self.widget.img_play, 'play')
        
        self._draw_animated_button(center_x + 60, btn_y, 
                                   self.widget.img_next, 'next')

    def _draw_animated_button(self, cx, cy, img, anim_key):
        state = self.widget.btn_anim[anim_key]
        self.painter.save()
        self.painter.translate(cx + state['offset'], cy)
        self.painter.scale(state['scale'], state['scale'])
        size = 40
        self.painter.drawPixmap(-size//2, -size//2, img)
        self.painter.restore()
    
    def _draw_visualizer(self, x, y, h, width_available, progress_ratio, 
                        bar_width=3, align_bottom=False):
        # Reverted to BAR Style (The "Old One") for Collapsed Mode
        self.painter.save()
        self.painter.setPen(Qt.PenStyle.NoPen)
        gap = 2
        total_bar_width = bar_width + gap
        num_bars = int(width_available / total_bar_width)
        num_bars = min(num_bars, self.widget.vis_count)
        
        c_played = COLOR_ACCENT
        c_upcoming = COLOR_BAR_BG
        
        for i in range(num_bars):
            val = self.widget.vis_bars[i]
            bar_h = val * h * self.widget.vis_multiplier
            
            bar_pos_ratio = i / max(1, num_bars)
            if bar_pos_ratio < progress_ratio:
                self.painter.setBrush(QBrush(c_played))
            else:
                self.painter.setBrush(QBrush(c_upcoming))
            
            bx = x + (i * total_bar_width)
            if align_bottom:
                self.painter.drawRoundedRect(QRectF(bx, y - bar_h, bar_width, bar_h), 1.5, 1.5)
            else:
                self.painter.drawRoundedRect(QRectF(bx, y - bar_h/2, bar_width, bar_h), 1.5, 1.5)
        self.painter.restore()

    def _draw_scrolling_text(self, rect, text, font, color):
        self.painter.save()
        self.painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        available_w = rect.width()
        
        self.widget.title_text_width = text_w
        self.widget.available_text_w = available_w
        self.widget.text_fits = (text_w <= available_w)
        
        self.painter.setClipRect(rect)
        if self.widget.text_fits:
            self.painter.setPen(QPen(color))
            self.painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        else:
            grad = QLinearGradient(rect.topLeft(), rect.topRight())
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 0))
            grad.setColorAt(0.1, color)
            grad.setColorAt(0.9, color)
            grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            self.painter.setPen(QPen(QBrush(grad), 0))
            
            draw_x = rect.x() - self.widget.scroll_x
            draw_rect = QRectF(draw_x, rect.y(), text_w + 50, rect.height())
            self.painter.drawText(draw_rect, 
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 
                                 text)
        self.painter.restore()