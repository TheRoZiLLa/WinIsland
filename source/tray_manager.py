from PyQt6.QtCore import Qt, QUrl, QMimeData, QPoint, QRectF
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QApplication
from config import TRAY_BUBBLE_SIZE, TRAY_BUBBLE_GAP

class TrayManager:
    """Manages file tray state, drag-and-drop, and interactions."""
    
    def __init__(self, parent_widget):
        self.widget = parent_widget
        self.files = []
        self.is_dragging_file = False
        self.minimized = False  # True = Show Notch, False = Show Grid
        
        self.tray_anim_timer = 0.0
        self.drag_start_pos = QPoint()
        
        # Liquid Pop Animation
        # 0.0 = Merged/Hidden, 1.0 = Fully Popped Out
        self.pop_anim_progress = 0.0 
        
        # Hover states
        self.tray_clear_hover = False
        self.tray_close_hover = False
        self.notch_hover = False
        
        # Layout Config
        self.grid_start_y = 60
        self.item_w = 70
        self.item_h = 80

    def has_files(self):
        return len(self.files) > 0

    def update_anim(self, dt):
        """Updates animation timers."""
        # 1. Dot animation for tray view
        self.tray_anim_timer = (self.tray_anim_timer + dt * 2.0) % 2.0
        
        # 2. Liquid Pop Animation
        target_pop = 1.0 if (self.minimized and self.has_files()) else 0.0
        
        # Smooth spring-like interpolation
        diff = target_pop - self.pop_anim_progress
        if abs(diff) > 0.001:
            self.pop_anim_progress += diff * 0.15
        else:
            self.pop_anim_progress = target_pop

    def handle_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.is_dragging_file = True
            # Temporarily un-minimize to show drop area
            self.minimized = False 
            self.widget.is_expanded = True
            self.widget.update()
        else:
            event.ignore()

    def handle_drag_leave(self, event):
        self.is_dragging_file = False
        # Auto-minimize on drag leave if files exist
        if self.has_files():
            self.minimized = True
            self.widget.is_expanded = False
        else:
            self.widget.is_expanded = False
        self.widget.update()

    def handle_drop(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                self.files.append(url.toLocalFile())
            self.is_dragging_file = False
            self.minimized = False
            self.widget.is_expanded = True
            self.widget.update()

    def handle_mouse_move(self, event):
        """
        Handles dragging files out of the tray.
        Returns True if a drag operation started (consumes event).
        """
        pos = event.position()
        
        # Check for drag start (only if expanded and not minimized)
        if len(self.files) > 0 and self.widget.is_expanded and not self.minimized:
            if (event.buttons() & Qt.MouseButton.LeftButton) and \
               (pos.toPoint() - self.drag_start_pos).manhattanLength() > QApplication.startDragDistance():
                
                # Hit test grid
                w = self.widget.width()
                cols = max(1, (w - 40) // self.item_w)
                
                file_to_drag = None
                drag_index = -1
                
                for i, file_path in enumerate(self.files):
                    row = i // cols
                    col = i % cols
                    x_pos = 20 + col * self.item_w
                    y_pos = self.grid_start_y + row * self.item_h
                    
                    item_rect = QRectF(x_pos, y_pos, 60, 60)
                    if item_rect.contains(pos):
                        file_to_drag = file_path
                        drag_index = i
                        break
                
                if file_to_drag:
                    drag = QDrag(self.widget)
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(file_to_drag)])
                    drag.setMimeData(mime)
                    
                    # Execute Drag
                    drag.exec(Qt.DropAction.CopyAction)
                    
                    # Remove file on drag out
                    if drag_index != -1 and drag_index < len(self.files):
                         self.files.pop(drag_index)
                         if len(self.files) == 0:
                             self.widget.is_expanded = False
                             self.minimized = False
                    
                    # If files remain, minimize back to notch after drag out
                    if len(self.files) > 0:
                        self.minimized = True
                        self.widget.is_expanded = False
                    
                    self.widget.update()
                    return True
        return False

    def check_hover(self, pos):
        """Updates hover states for tray elements."""
        w = self.widget.width()
        
        # 1. Expanded Mode Hovers
        if self.widget.is_expanded and not self.minimized:
            # Clear Button (Top Right)
            clear_btn_rect = QRectF(w - 70, 10, 50, 20)
            self.tray_clear_hover = clear_btn_rect.contains(pos)
            
            # Close "X" Button (Left of Clear)
            close_btn_rect = QRectF(w - 100, 10, 20, 20)
            self.tray_close_hover = close_btn_rect.contains(pos)
            self.notch_hover = False
            
        # 2. Minimized/Notch Mode Hovers
        elif self.minimized and self.has_files():
            # If minimized, calculate actual visual position of bubble
            # We assume animation is at 1.0 (fully popped) if checking hover
            bubble_rect = QRectF(w - TRAY_BUBBLE_SIZE - 5, 0, TRAY_BUBBLE_SIZE + 5, self.widget.height())
            self.notch_hover = bubble_rect.contains(pos)
            self.tray_clear_hover = False
            self.tray_close_hover = False
        else:
            self.tray_clear_hover = False
            self.tray_close_hover = False
            self.notch_hover = False

    def set_drag_start(self, pos):
        self.drag_start_pos = pos

    def handle_click(self, pos):
        """
        Handles clicks on tray elements.
        Returns True if the click was handled.
        """
        has_files = len(self.files) > 0
        
        # Case A: Minimized Notch Click
        if has_files and self.minimized:
            if self.notch_hover:
                self.minimized = False
                self.widget.is_expanded = True
                self.widget.update()
                return True

        # Case B: Expanded Tray Clicks
        if self.widget.is_expanded and has_files and not self.minimized:
            # 1. Clear Button
            if self.tray_clear_hover:
                self.files = []
                self.minimized = False # No files left
                self.widget.is_expanded = False # Collapse
                self.widget.update()
                return True
            
            # 2. Close "X" Button
            if self.tray_close_hover:
                self.minimized = True
                self.widget.is_expanded = False # Visual collapse to notch
                self.widget.update()
                return True

            # 3. Grid Area (Eat clicks so main window doesn't toggle)
            if pos.y() > self.grid_start_y:
                return True

        return False