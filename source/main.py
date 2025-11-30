import sys
from PyQt6.QtWidgets import QApplication
from media_widget import DynamicIsland

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = DynamicIsland()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()