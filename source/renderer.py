from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QPainter, QBrush, QPen, QFont, QPainterPath, 
                         QLinearGradient, QColor, QFontMetrics, QPixmap)

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
        range_h = EXPAND_H - IDLE_H
        curr_off = self.widget.current_h - IDLE_H
        self.progress = max(0.0, min(1.0, curr_off / range_h))
        
        self.progress_ratio = 0.0
        if self.widget.media_dur > 0:
            self.progress_ratio = self.widget.display_pos / self.widget.media_dur
        
        self.clip_path = self._create_clip_path()
        
        self._render_background()
        
        # New unified rendering approach for smooth transitions
        if self.widget.title_text != "Idle":
            self._render_interpolating_album_art()
        
        self._render_collapsed_content()
        self._render_expanded_content()
        
        self.painter.end()
    
    def _create_clip_path(self):
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
        show_expanded_bg = (self.widget.is_expanded and self.widget.title_text != "Idle")
        
        if show_expanded_bg:
            self.painter.save()
            self.painter.setClipPath(self.clip_path)
            self.painter.setOpacity(self.progress)
            
            # --- New Logic: Use 5-Color Gradient Instead of Image ---
            if self.widget.current_album_art:
                img = self.widget.current_album_art.toImage()
                w, h = img.width(), img.height()
                
                # Sample 5 distinct points for colors
                c1 = img.pixelColor(w // 2, h // 2)       # Center
                c2 = img.pixelColor(w // 4, h // 4)       # Top-Leftish
                c3 = img.pixelColor(3 * w // 4, h // 4)   # Top-Rightish
                c4 = img.pixelColor(w // 4, 3 * h // 4)   # Bottom-Leftish
                c5 = img.pixelColor(3 * w // 4, 3 * h // 4) # Bottom-Rightish
                
                # Create gradient using these 5 colors
                grad = QLinearGradient(0, 0, self.w, self.h)
                grad.setColorAt(0.0, c2)
                grad.setColorAt(0.25, c3)
                grad.setColorAt(0.5, c1)
                grad.setColorAt(0.75, c4)
                grad.setColorAt(1.0, c5)
                
                # Fill background with gradient
                self.painter.fillRect(0, 0, self.w, self.h, grad)
                
                # 2. Dark Overlay + More Black Gradient (Keep this for readability)
                self.painter.fillRect(0, 0, self.w, self.h, QColor(0, 0, 0, 100)) # Base dimming
                
                grad_black = QLinearGradient(0, 0, 0, self.h)
                grad_black.setColorAt(0.0, QColor(0, 0, 0, 0))
                grad_black.setColorAt(0.3, QColor(0, 0, 0, 40)) # Start darkening earlier
                grad_black.setColorAt(0.7, QColor(0, 0, 0, 180)) # Much darker at bottom text area
                grad_black.setColorAt(1.0, QColor(0, 0, 0, 255)) # Pure black at bottom
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
        """
        Calculates and draws the album art at a position interpolated between
        its collapsed state (small icon) and expanded state (jewel case).
        """
        if not self.widget.current_album_art:
            return

        # --- Define Start State (Collapsed) ---
        # Centered vertically in the 35px height bar
        start_size = 24
        start_x = 15
        start_y = (IDLE_H - start_size) / 2 # ~5.5px
        
        # --- Define End State (Expanded) ---
        # Jewel Case position logic from _render_cd_layout
        # We need to recalculate the final dimensions here to interpolate to them
        max_box_h = 130
        max_box_w = 180 
        
        # Calculate aspect ratio scaling for the target
        scaled_pix = self.widget.current_album_art.scaled(
            int(max_box_w), int(max_box_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        end_w = scaled_pix.width()
        end_h = scaled_pix.height()
        end_x = 25
        end_y = (self.h - end_h) // 2 - 10
        
        # --- Interpolate ---
        # We use a cubic easing for smoother pop
        t = self.progress
        t = t * t * (3 - 2 * t) # Smoothstep
        
        curr_w = start_size + (end_w - start_size) * t
        curr_h = start_size + (end_h - start_size) * t
        curr_x = start_x + (end_x - start_x) * t
        
        # Y is tricky because self.h changes.
        # We want it relative to the visual top, but center alignment changes
        # Simple interpolation of absolute Y might look jerky if window height grows fast.
        # Instead, let's interpolate the "center Y" relative to current height
        # start_center_y = IDLE_H / 2
        # end_center_y = (self.h // 2) - 10 + (end_h / 2) # Roughly center of box
        
        curr_y = start_y + (end_y - start_y) * t
        
        # --- Draw The Box/Art ---
        self.painter.save()
        
        # 1. CD Behind (Only visible as we expand)
        # Fade in CD as we expand
        if self.progress > 0.1:
            cd_opacity = (self.progress - 0.1) / 0.9
            # Also apply the text_change opacity for smooth track transitions
            self.painter.setOpacity(cd_opacity * self.widget.text_change_progress)
            
            cd_size = 140
            # Interpolate CD X position too so it slides out from behind
            # Start CD at same X as box, end at box + offset
            target_cd_x = end_x + CD_OFFSET_X
            curr_cd_x = curr_x + (target_cd_x - end_x) * t
            
            cd_y_pos = (self.h - cd_size) // 2 - 10
            
            # Draw spinning CD
            center_x = curr_cd_x + cd_size/2
            center_y = cd_y_pos + cd_size/2
            
            self.painter.save()
            self.painter.translate(center_x, center_y)
            self.painter.rotate(self.widget.cd_rotation)
            self.painter.translate(-center_x, -center_y)
            
            if self.widget.img_cd:
                self.painter.drawPixmap(int(curr_cd_x), int(cd_y_pos), int(cd_size), int(cd_size), self.widget.img_cd)
            
            # CD Center sticker
            art_diam = int(cd_size * 0.4)
            art_x = center_x - art_diam/2
            art_y = center_y - art_diam/2
            path = QPainterPath()
            path.addEllipse(QRectF(art_x, art_y, art_diam, art_diam))
            self.painter.setClipPath(path)
            self.painter.drawPixmap(int(art_x), int(art_y), art_diam, art_diam, self.widget.current_album_art)
            self.painter.restore()

        # 2. Main Art Box (Interpolated)
        # Apply fade animation from logic
        box_opacity = 1.0
        if self.progress > 0.8: # Fully expanded
             box_opacity = self.widget.box_fade_anim
        self.painter.setOpacity(box_opacity)

        # Shadow (only when getting bigger)
        if self.progress > 0.2:
            self.painter.setPen(Qt.PenStyle.NoPen)
            # FIX: Ensure alpha is an integer
            shadow_alpha = int(100 * self.progress)
            self.painter.setBrush(QBrush(QColor(0, 0, 0, shadow_alpha)))
            self.painter.drawRoundedRect(QRectF(curr_x+4*t, curr_y+4*t, curr_w, curr_h), 4, 4)

        # The Image
        path = QPainterPath()
        path.addRoundedRect(QRectF(curr_x, curr_y, curr_w, curr_h), 4, 4)
        self.painter.setClipPath(path)
        self.painter.drawPixmap(QRectF(curr_x, curr_y, curr_w, curr_h).toRect(), 
                               self.widget.current_album_art)
        
        # Gloss (only visible when larger)
        if self.progress > 0.5:
            grad = QLinearGradient(curr_x, curr_y, curr_x + curr_w, curr_y + curr_h)
            # FIX: Ensure alpha is an integer
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
        center_y = self.h / 2
        
        if self.w > 120:
            # Animation State (0.0 to 1.0)
            anim_progress = self.widget.temp_mode_progress 
            
            # --- Time Display (Leaving or Entering) ---
            if anim_progress < 0.99:
                self.painter.save()
                time_scale = 0.6 + (0.4 * (1.0 - anim_progress))
                time_opacity = 1.0 - anim_progress
                
                self.painter.translate(self.w/2, self.h/2)
                self.painter.scale(time_scale, time_scale)
                self.painter.translate(-self.w/2, -self.h/2)
                self.painter.setOpacity(max(0.0, opacity * time_opacity))
                
                self.painter.setPen(QPen(COLOR_TEXT_MAIN))
                self.painter.setFont(QFont(FONT_FAMILY, 10, QFont.Weight.Bold))
                self.painter.drawText(QRectF(0, 0, self.w, self.h), 
                                     Qt.AlignmentFlag.AlignCenter, 
                                     self.widget.display_time)
                self.painter.restore()
            
            # --- Title Display (Entering or Leaving) ---
            if anim_progress > 0.01:
                self.painter.save()
                title_scale = 0.6 + (0.4 * anim_progress)
                title_opacity = anim_progress
                
                self.painter.translate(self.w/2, self.h/2)
                self.painter.scale(title_scale, title_scale)
                self.painter.translate(-self.w/2, -self.h/2)
                self.painter.setOpacity(max(0.0, opacity * title_opacity))
                
                title_rect = QRectF(45, 0, self.w-90, self.h)
                self._draw_scrolling_text(title_rect, self.widget.title_text, 
                                         QFont(FONT_FAMILY, 10, QFont.Weight.Bold), 
                                         COLOR_TEXT_MAIN)
                self.painter.restore()

        if self.widget.title_text != "Idle":
            # NOTE: We removed the static album art drawing here because
            # _render_interpolating_album_art now handles drawing it at small scale too.
            
            vis_w = 30
            vis_x = self.w - vis_w - 15
            if self.widget.vis_multiplier > 0.01:
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
            self._render_cd_layout_controls_only()
        
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
    
    def _render_cd_layout_controls_only(self):
        """
        Renders ONLY the text and controls for the CD layout.
        The Album Art and CD itself are handled by _render_interpolating_album_art
        to allow for smooth transitioning.
        """
        content_x = 220
        content_w = self.w - content_x - 20
        
        # Track Change Animation (Scale/Fade)
        text_scale = 0.8 + (0.2 * self.widget.text_change_progress)
        text_opacity = self.widget.text_change_progress
        
        self.painter.save()
        cx_text = content_x + content_w / 2
        cy_text = 45 
        self.painter.translate(cx_text, cy_text)
        self.painter.scale(text_scale, text_scale)
        self.painter.translate(-cx_text, -cy_text)
        self.painter.setOpacity(text_opacity)

        text_rect = QRectF(content_x, 30, content_w, 30)
        self._draw_scrolling_text(text_rect, self.widget.title_text, 
                                 QFont(FONT_FAMILY, FONT_SIZE_TITLE, QFont.Weight.Bold), 
                                 COLOR_TEXT_MAIN)
        
        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont(FONT_FAMILY, FONT_SIZE_ARTIST))
        self.painter.drawText(QRectF(content_x, 55, content_w, 20), 
                             Qt.AlignmentFlag.AlignCenter, 
                             self.widget.artist_text)
        self.painter.restore()

        self._render_progress_bar_cd_style(content_x, content_w)
        self._render_control_buttons_cd_style(content_x, content_w)

    def _render_progress_bar_cd_style(self, x, w):
        bar_y = self.h - BARYPOS
        
        if self.widget.vis_multiplier > 0.01:
            self._draw_visualizer(x, bar_y - 8, 25, w, self.progress_ratio, 
                                 bar_width=5, align_bottom=True)
        
        anim_height = 4.0 + (4.0 * self.widget.bar_hover_anim)
        anim_radius = anim_height / 2.0
        draw_y = (bar_y - 6) - (anim_height / 2.0)
        
        self.painter.setPen(Qt.PenStyle.NoPen)
        self.painter.setBrush(QBrush(COLOR_BAR_BG))
        self.painter.drawRoundedRect(QRectF(x, draw_y, w, anim_height), 
                                     anim_radius, anim_radius)
        
        if self.widget.media_dur > 0:
            prog_bar = min(1.0, max(0.0, self.widget.display_pos / self.widget.media_dur))
            fill_w = w * prog_bar
            self.painter.setBrush(QBrush(COLOR_TEXT_MAIN))
            self.painter.drawRoundedRect(QRectF(x, draw_y, fill_w, anim_height), 
                                        anim_radius, anim_radius)
            
            handle_radius = 4.0 + (1.0 * self.widget.bar_hover_anim)
            self.painter.drawEllipse(QPointF(x + fill_w, bar_y - 6), 
                                    handle_radius, handle_radius)

        self.painter.setPen(QPen(COLOR_TEXT_SUB))
        self.painter.setFont(QFont(FONT_FAMILY, FONT_SIZE_TIME, QFont.Weight.Bold))
        curr_time_str = format_time(self.widget.display_pos)
        total_time_str = format_time(self.widget.media_dur)
        self.painter.drawText(int(x), int(bar_y + 15), curr_time_str)
        self.painter.drawText(int(x + w - 30), int(bar_y + 15), total_time_str)

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