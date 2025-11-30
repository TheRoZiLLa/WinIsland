import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QBrush, QPixmap, QPainterPath


def load_or_create_icon(filename, fallback_name, size=40, color=Qt.GlobalColor.white):
    """
    Load an icon from file or create a fallback icon.
    
    Args:
        filename: Path to icon file
        fallback_name: Type of fallback icon ('play', 'pause', 'next', 'prev')
        size: Icon size in pixels
        color: Icon color
        
    Returns:
        QPixmap: The loaded or generated icon
    """
    if os.path.exists(filename):
        pixmap = QPixmap(filename)
        if not pixmap.isNull():
            return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, 
                               Qt.TransformationMode.SmoothTransformation)
    
    # Create fallback icon
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


def format_time(seconds):
    """
    Format seconds into M:SS format.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        str: Formatted time string
    """
    if seconds < 0:
        return "0:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"