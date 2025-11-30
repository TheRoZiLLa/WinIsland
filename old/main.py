import sys
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QIcon, QPixmap, QPainterPath

# Import the Widget
from media_widget import MediaWidget, COLOR_BG

# --- Configuration (Window Specific) ---
IDLE_W, IDLE_H = 200, 35        
HOVER_W, HOVER_H = 230, 42      
EXPAND_W, EXPAND_H = 450, 190

# Media Specific Widths (Used for physics calc)
MEDIA_IDLE_W = 300
MEDIA_TEMP_W = 350 # Width when showing title temporarily
MEDIA_HOVER_W = 330

CORNER_RADIUS = 800              
SPRING_STIFFNESS = 0.15
SPRING_DAMPING = 0.62

class DynamicIsland(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        self.screen_width = QApplication.primaryScreen().size().width()
        
        # Physics State
        self.current_w = float(IDLE_W)
        self.current_h = float(IDLE_H)
        self.target_w = float(IDLE_W)
        self.target_h = float(IDLE_H)
        self.vel_w = 0.0
        self.vel_h = 0.0
        
        self.is_expanded = False
        self.is_hovered = False
        self.display_time = ""
        
        # Initialize Media Logic
        self.media_widget = MediaWidget()
        self.media_widget.request_update.connect(self.update)
        
        # Timers
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.game_loop)
        self.anim_timer.start(16) # 60 FPS
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_text)
        self.clock_timer.start(1000)
        
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

    def update_clock_text(self):
        now = datetime.now()
        am_pm = now.strftime("%p").replace("AM", "A.M.").replace("PM", "P.M.")
        self.display_time = now.strftime(f"%I:%M - {am_pm}")

    def game_loop(self):
        # 1. Window Physics
        self.animate_spring()
        # 2. Media Physics
        self.media_widget.tick(self.is_expanded, self.is_hovered)

    def animate_spring(self):
        # Calculate target based on media state
        has_media = (self.media_widget.title_text != "Idle")
        
        # Logic for "Temp Mode" width expansion
        current_idle_w = MEDIA_IDLE_W + (MEDIA_TEMP_W - MEDIA_IDLE_W) * self.media_widget.temp_mode_progress
        
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

    def mouseMoveEvent(self, event):
        # Delegate hover detection to media widget
        self.media_widget.handle_mouse_move(event.position(), self.width(), self.height(), self.is_expanded)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            
            # 1. Delegate click to media widget
            if self.is_expanded:
                handled = self.media_widget.handle_mouse_press(event.position(), self.width(), self.height())
                if handled:
                    return
            
            # 2. If not handled, toggle expansion
            self.is_expanded = not self.is_expanded
            self.vel_w += 10 if self.is_expanded else -5
            self.vel_h += 10 if self.is_expanded else -5

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
        
        # 1. Background (Possibly Art)
        art_drawn = False
        if self.is_expanded:
             art_drawn = self.media_widget.paint_background_art(p, w, h, path, progress)
        
        if not art_drawn:
             p.setBrush(QBrush(COLOR_BG))
             p.setPen(Qt.PenStyle.NoPen)
             p.drawPath(path)
        elif progress < 1.0:
            # Fade black over art if collapsing
            p.save()
            p.setOpacity(1.0 - progress)
            p.setBrush(QBrush(COLOR_BG))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.restore()

        # 2. Collapsed Content
        if progress < 0.8:
            p.save()
            opacity = 1.0 - (progress * 3) 
            p.setOpacity(max(0.0, opacity))
            self.media_widget.paint_collapsed_content(p, w, h, opacity, self.display_time)
            p.restore()

        # 3. Expanded Content
        if progress > 0.2:
            p.save()
            opacity = (progress - 0.2) / 0.8
            p.setOpacity(max(0.0, min(1.0, opacity)))
            self.media_widget.paint_expanded_content(p, w, h, opacity, self.display_time)
            p.restore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = DynamicIsland()
    window.show()
    
    sys.exit(app.exec())