from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QPainter, QBrush, QPen, QFont, QPainterPath, 
                         QLinearGradient, QColor, QFontMetrics)

from config import *
from helpers import format_time


class MediaRenderer:
    """Handles all rendering for the Dynamic Island widget."""
    
    def __init__(self, widget):
        self.widget = widget
        self.painter = QPainter(widget)
        self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        self.w = widget.width()
        self.h = widget.height()
        
    def render(self):
        """Main rendering entry point."""
        # Calculate progress and ratios
        range_h = EXPAND_H - IDLE_H
        curr_off = self.widget.current_h - IDLE_H
        self.progress = max(0.0, min(1.0, curr_off / range_h))
        
        self.progress_ratio = 0.0
        if self.widget.media_dur > 0:
            self.progress_ratio = self.widget.display_pos / self.widget.media_dur
        
        # Create clip path
        self.clip_path = self._create_clip_path()
        
        # Render layers
        self._render_background()
        self._render_collapsed_content()
        self._render_expanded_content()
        
        self.painter.end()
    
    def _create_clip_path(self):
        """Create the rounded rectangle clip path."""
        path = QPainterPath()
        safe_radius = min(CORNER_RADIUS, self.h)
        
        path.moveTo(0, 0)
        path.lineTo(self.w, 0)
        path.lineTo(self.w, self.h - safe_radius)
        path.cubicTo(self.w, self.h, self.w, self.h, self.w - safe_radius, self.h)
        path.lineTo(safe_radius, self.h)
        path.cubicTo(0, self.h, 0, self.h, 0, self.h - safe_radius)
        path.lineTo(0, 0)
        
        return path
    
    def _render_background(self):
        """Render background with album art or solid color."""
        show_bg = (self.widget.is_expanded and 
                   self.widget.title_text != "Idle" and 
                   (self.widget.current_album_art or 
                    (self.widget.is_fading_art and self.widget.prev_album_art)))
        
        if show_bg:
            self.painter.save()
            self.painter.setClipPath(self.clip_path)
            self.painter.setOpacity(self.progress)
            
            # Draw album art background
            if self.widget.is_fading_art and self.widget.prev_album_art:
                self._draw_album_cover(self.widget.prev_album_art, 1.0)
                self._draw_album_cover(self.widget.current_album_art, self.widget.art_fade_progress)
            else:
                self._draw_album_cover(self.widget.current_album_art, 1.0)

            # Draw overlays
            self.painter.fillRect(0, 0, self.w, self.h, QColor(0, 0, 0, 80))
            
            grad = QLinearGradient(0, 0, 0, self.h)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.6, QColor(0, 0, 0, 180))
            grad.setColorAt(0.85, QColor(0, 0, 0, 255))
            grad.setColorAt(1.0, QColor(0, 0, 0, 255))
            self.painter.fillRect(0, 0, self.w, self.h, grad)
            self.painter.restore()
            
            # Fade to solid during expansion
            if self.progress < 1.0:
                self.painter.save()
                self.painter.setOpacity(1.0 - self.progress)
                self.painter.setBrush(QBrush(COLOR_BG))
                self.painter.setPen(Qt.PenStyle.NoPen)
                self.painter.drawPath(self.clip_path)
                self.painter.restore()
        else:
            # Solid background
            self.painter.setBrush(QBrush(COLOR_BG))
            self.painter.setPen(Qt.PenStyle.NoPen)
            self.painter.drawPath(self.clip_path)
    
    def _draw_album_cover(self, pix, opacity):
        """Draw album cover as background."""
        if not pix:
            return
            
        self.painter.save()
        if opacity < 1.0:
            self.painter.setOpacity(self.progress * opacity)
        else:
            self.painter.setOpacity(self.progress)

        img_w = pix.width()
        img_h = pix.height()
        scale_factor = self.h / img_h
        if (img_w * scale_factor) < self.w:
            scale_factor = self.w / img_w
        new_w = int(img_w * scale_factor)
        new_h = int(img_h * scale_factor)
        x_off = (self.w - new_w) / 2
        y_off = (self.h - new_h) / 2
        self.painter.drawPixmap(int(x_off), int(y_off), new_w, new_h, pix, 0, 0, img_w, img_h)
        self.painter.restore()
    
    def _render_collapsed_content(self):
        """Render content when widget is collapsed."""
        if self.progress >= 0.8:
            return
            
        self.painter.save()
        opacity = 1.0 - (self.progress * 3)
        self.painter.setOpacity(max(0.0, opacity))
        center_y = self.h / 2
        
        # Center text area
        if self.w > 120:
            t_val = self.widget.temp_mode_progress
            
            # Time display
            if t_val < 0.99:
                self.painter.save()
                time_opacity = 1.0 - t_val
                time_scale = 1.0 - (0.3 * t_val)
                self.painter.setOpacity(max(0.0, time_opacity * opacity))
                self.painter.translate(self.w/2, self.h/2)
                self.painter.scale(time_scale, time_scale)
                self.painter.translate(-self.w/2, -self.h/2)
                self.painter.setPen(QPen(COLOR_TEXT_MAIN))
                self.painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                self.painter.drawText(QRectF(0, 0, self.w, self.h), 
                                     Qt.AlignmentFlag.AlignCenter, 
                                     self.widget.display_time)
                self.painter.restore()
            
            # Title display (scrolling)
            if t_val > 0.01:
                self.painter.save()
                title_opacity = t_val
                title_scale = 0.7 + (0.3 * t_val)
                self.painter.setOpacity(max(0.0, title_opacity * opacity))
                self.painter.translate(self.w/2, self.h/2)
                self.painter.scale(title_scale, title_scale)
                self.painter.translate(-self.w/2, -self.h/2)
                
                title_rect = QRectF(45, 0, self.w-90, self.h)
                self._draw_scrolling_text(title_rect, self.widget.title_text, 
                                         QFont("Segoe UI", 10, QFont.Weight.Bold), 
                                         COLOR_TEXT_MAIN)
                self.painter.restore()

        if self.widget.title_text != "Idle":
            # Album art thumbnail
            self._draw_collapsed_album_art(center_y)
            
            # Visualizer
            self._draw_collapsed_visualizer(center_y)
        
        self.painter.restore()
    
    def _draw_collapsed_album_art(self, center_y):
        """Draw small album art thumbnail in collapsed mode."""
        art_size = 24
        art_x = 15
        art_y = int(center_y - art_size/2)
        
        self.painter.save()
        draw_pix = self.widget.current_album_art
        scale_anim_x = 1.0
        scale_anim_y = 1.0
        
        if self.widget.is_flipping_art:
            center_art_x = art_x + art_size/2
            center_art_y = art_y + art_size/2
            self.painter.translate(center_art_x, center_art_y)
            
            if self.widget.art_flip_progress < 0.5:
                draw_pix = self.widget.prev_album_art
                scale_anim_x = 1.0 - (self.widget.art_flip_progress * 2)
                scale_anim_y = 1.0 - (self.widget.art_flip_progress * 0.6)
            else:
                draw_pix = self.widget.current_album_art
                scale_anim_x = (self.widget.art_flip_progress - 0.5) * 2
                scale_anim_y = 0.7 + ((self.widget.art_flip_progress - 0.5) * 0.6)
            
            self.painter.scale(scale_anim_x, scale_anim_y)
            self.painter.translate(-center_art_x, -center_art_y)
        
        if draw_pix:
            art_path = QPainterPath()
            art_path.addRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
            self.painter.setClipPath(art_path)
            self.painter.drawPixmap(art_x, art_y, art_size, art_size, draw_pix)
        else:
            self.painter.setBrush(QBrush(QColor(40, 40, 40)))
            self.painter.drawRoundedRect(QRectF(art_x, art_y, art_size, art_size), 4, 4)
        
        self.painter.restore()
    
    def _draw_collapsed_visualizer(self, center_y):
        """Draw visualizer or dot in collapsed mode."""
        vis_w = 30
        vis_x = self.w - vis_w - 15
        
        if self.widget.vis_multiplier > 0.01:
            self._draw_visualizer(vis_x, center_y, 14, vis_w, self.progress_ratio, 
                                 bar_width=3, align_bottom=False)
        else:
            dot_size = 6
            self.painter.setBrush(QBrush(COLOR_ACCENT))
            self.painter.drawEllipse(QPointF(vis_x + vis_w/2, center_y), 
                                    dot_size/2, dot_size/2)
    
    def _render_expanded_content(self):
        """Render content when widget is expanded."""
        if self.progress <= 0.2:
            return
            
        self.painter.save()
        opacity = (self.progress - 0.2) / 0.8
        self.painter.setOpacity(max(0.0, min(1.0, opacity)))

        if self.widget.title_text == "Idle":
            self._render_idle_state()
        else:
            self._render_media_state()
        
        self.painter.restore()
    
    def _render_idle_state(self):
        """Render idle/clock display."""
        self.painter.setPen(QPen(COLOR_TEXT_MAIN))
        self.painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.painter.drawText(QRectF(0, 0, self.w, self.h), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.display_time)
        
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont("Segoe UI", 10))
        self.painter.drawText(QRectF(0, 40, self.w, self.h), 
                             Qt.AlignmentFlag.AlignCenter, 
                             "No Media Playing")
    
    def _render_media_state(self):
        """Render media controls and info."""
        # Time at top
        self.painter.setPen(QPen(QColor(255, 255, 255, 150)))
        self.painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.painter.drawText(QRectF(0, 8, self.w, 20), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.display_time)

        # Title with scrolling
        text_rect = QRectF(20, 30, self.w - 40, 30)
        self._draw_scrolling_text(text_rect, self.widget.title_text, 
                                 QFont("Segoe UI", 13, QFont.Weight.Bold), 
                                 COLOR_TEXT_MAIN)
        
        # Artist
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont("Segoe UI", 9))
        self.painter.drawText(QRectF(20, 55, self.w-40, 20), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.artist_text)

        # Progress bar and visualizer
        self._render_progress_bar()
        
        # Control buttons
        self._render_control_buttons()
    
    def _render_progress_bar(self):
        """Render progress bar with visualizer."""
        bar_y = self.h - BARYPOS
        bar_x = 60
        bar_w = self.w - 120
        
        # Draw visualizer behind bar
        if self.widget.vis_multiplier > 0.01:
            self._draw_visualizer(bar_x, bar_y - 8, 25, bar_w, self.progress_ratio, 
                                 bar_width=5, align_bottom=True)
        
        # Animated progress bar
        anim_height = 4.0 + (4.0 * self.widget.bar_hover_anim)
        anim_radius = anim_height / 2.0
        draw_y = (bar_y - 6) - (anim_height / 2.0)
        
        self.painter.setPen(Qt.PenStyle.NoPen)
        self.painter.setBrush(QBrush(COLOR_BAR_BG))
        self.painter.drawRoundedRect(QRectF(bar_x, draw_y, bar_w, anim_height), 
                                     anim_radius, anim_radius)
        
        if self.widget.media_dur > 0:
            prog_bar = min(1.0, max(0.0, self.widget.display_pos / self.widget.media_dur))
            fill_w = bar_w * prog_bar
            self.painter.setBrush(QBrush(COLOR_TEXT_MAIN))
            self.painter.drawRoundedRect(QRectF(bar_x, draw_y, fill_w, anim_height), 
                                        anim_radius, anim_radius)
            
            handle_radius = 4.0 + (1.0 * self.widget.bar_hover_anim)
            self.painter.drawEllipse(QPointF(bar_x + fill_w, bar_y - 6), 
                                    handle_radius, handle_radius)

        # Time labels
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        curr_time_str = format_time(self.widget.display_pos)
        total_time_str = format_time(self.widget.media_dur)
        self.painter.drawText(20, bar_y, curr_time_str)
        self.painter.drawText(self.w - 50, bar_y, total_time_str)
    
    def _render_control_buttons(self):
        """Render playback control buttons."""
        center_x = self.w / 2
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
        """Draw a button with scale and offset animation."""
        state = self.widget.btn_anim[anim_key]
        self.painter.save()
        self.painter.translate(cx + state['offset'], cy)
        self.painter.scale(state['scale'], state['scale'])
        size = 40
        self.painter.drawPixmap(-size//2, -size//2, img)
        self.painter.restore()
    
    def _draw_visualizer(self, x, y, h, width_available, progress_ratio, 
                        bar_width=3, align_bottom=False):
        """Draw audio visualizer bars."""
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
        """Draw text with scrolling animation."""
        self.painter.save()
        self.painter.setFont(font)
        fm = QFontMetrics(font)
        
        text_w = fm.horizontalAdvance(text)
        available_w = rect.width()
        
        # Update widget metrics
        self.widget.title_text_width = text_w
        self.widget.available_text_w = available_w
        self.widget.text_fits = (text_w <= available_w)
        
        self.painter.setClipRect(rect)
        
        if self.widget.text_fits:
            self.painter.setPen(QPen(color))
            self.painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        else:
            # Create gradient for smooth edge fade
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