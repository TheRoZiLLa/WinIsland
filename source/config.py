from PyQt6.QtGui import QColor

# Window Dimensions
IDLE_W, IDLE_H = 200, 35        
HOVER_W, HOVER_H = 230, 42      
EXPAND_W, EXPAND_H = 520, 220 

# Media Specific Widths
MEDIA_IDLE_W = 300
MEDIA_TEMP_W = 350
MEDIA_HOVER_W = 330

# Animation Settings
TEMP_MODE_DURATION = 5.0
CORNER_RADIUS = 800            
SPRING_STIFFNESS = 0.15
SPRING_DAMPING = 0.62

# Layout Positions
BARYPOS = 70
BTNYPOS = 40
CD_OFFSET_X = 80 # Config for CD position relative to album box X

# Fonts
FONT_FAMILY = "Segoe UI"
FONT_SIZE_CLOCK = 24
FONT_SIZE_TITLE = 13
FONT_SIZE_ARTIST = 9
FONT_SIZE_TIME = 8

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
IMG_CD_FILE = "asset/cd.png"