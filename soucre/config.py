from PyQt6.QtGui import QColor

# Window Dimensions
IDLE_W, IDLE_H = 200, 35        
HOVER_W, HOVER_H = 230, 42      
EXPAND_W, EXPAND_H = 450, 190

# Media Specific Widths
MEDIA_IDLE_W = 300
MEDIA_TEMP_W = 350  # Width when showing title temporarily
MEDIA_HOVER_W = 330

# Animation Settings
TEMP_MODE_DURATION = 5.0  # Seconds to show title on track change
CORNER_RADIUS = 800              
SPRING_STIFFNESS = 0.15
SPRING_DAMPING = 0.62

# Layout Positions
BARYPOS = 70
BTNYPOS = 40

# Colors
COLOR_BG = QColor("#000000")
COLOR_ACCENT = QColor("#FFFFFF") 
COLOR_PAUSED = QColor("#FF9500")
COLOR_TEXT_MAIN = QColor("#FFFFFF")
COLOR_TEXT_SUB = QColor("#DDDDDD")
COLOR_BAR_BG = QColor(255, 255, 255, 50)

# Icon Files
IMG_PLAY_FILE = "asset/play.png"
IMG_PAUSE_FILE = "asset/pause.png"
IMG_NEXT_FILE = "asset/next.png"
IMG_PREV_FILE = "asset/prev.png"