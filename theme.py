import sys
if sys.platform == 'win32':
    import winreg

from config import THEME_REG_KEY

def get_stylesheet(theme='dark'):
    if theme == 'light':
        return """
            QWidget { background-color: #f0f2f5; color: #1c1e21; font-family: 'Segoe UI', Arial, sans-serif; }
            QMainWindow { background-color: #ffffff; }
            QTabWidget::pane { border: none; }
            QTabBar::tab { background-color: #f0f2f5; color: #606770; padding: 12px 20px; border: none; font-weight: bold; font-size: 10pt; border-bottom: 3px solid transparent; }
            QTabBar::tab:selected { color: #1b74e4; border-bottom: 3px solid #1b74e4; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit { background-color: #ffffff; color: #1c1e21; border: 1px solid #ccd0d5; border-radius: 6px; padding: 8px; font-size: 10pt; }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus { border: 1px solid #1b74e4; }
            QPushButton { background-color: #e4e6eb; color: #1c1e21; font-weight: bold; padding: 10px 15px; border: none; border-radius: 6px; font-size: 10pt; }
            QPushButton:hover { background-color: #d8dbdf; }
            QPushButton:disabled { background-color: #f0f2f5; color: #bec3c9; }
            QPushButton#backup_button { background-color: #42b72a; color: white; }
            QPushButton#backup_button:hover { background-color: #36a420; }
            QPushButton#restore_button { background-color: #fa383e; color: white; }
            QPushButton#restore_button:hover { background-color: #e0282e; }
            QPushButton#manage_button { background-color: #1b74e4; color: white; }
            QPushButton#manage_button:hover { background-color: #155ab3; }
            QPushButton#save_needed_button { background-color: #42b72a; color: white; }
            QPushButton#save_needed_button:hover { background-color: #36a420; }
            QProgressBar { border: 1px solid #ccd0d5; border-radius: 6px; text-align: center; color: #1c1e21; }
            QProgressBar::chunk { background-color: #1b74e4; border-radius: 6px; }
            QLabel#header { font-size: 12pt; font-weight: bold; color: #1c1e21; }
            QLabel#version_ok { background-color: #e9f5e9; color: #36a420; border: 1px solid #a7d7a7; border-radius: 6px; padding: 8px; }
            QLabel#version_update { background-color: #fffbe6; color: #f0a300; border: 1px solid #ffecb3; border-radius: 6px; padding: 8px; }
            QFrame#separator { background-color: #ccd0d5; }
            QListWidget { border: 1px solid #ccd0d5; border-radius: 6px; background-color: #ffffff; }
            QListWidget::item { padding: 10px; }
            QGroupBox { border: 1px solid #ccd0d5; border-radius: 6px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        """
    else: # Dark theme
        return """
            QWidget { background-color: #18191a; color: #e4e6eb; font-family: 'Segoe UI', Arial, sans-serif; }
            QTabWidget::pane { border: none; }
            QTabBar::tab { background-color: #18191a; color: #b0b3b8; padding: 12px 20px; border: none; font-weight: bold; font-size: 10pt; border-bottom: 3px solid transparent; }
            QTabBar::tab:selected { color: #2d88ff; border-bottom: 3px solid #2d88ff; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit { background-color: #3a3b3c; color: #e4e6eb; border: 1px solid #3a3b3c; border-radius: 6px; padding: 8px; font-size: 10pt; }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus { border: 1px solid #2d88ff; }
            QPushButton { background-color: #3a3b3c; color: #e4e6eb; font-weight: bold; padding: 10px 15px; border: none; border-radius: 6px; font-size: 10pt; }
            QPushButton:hover { background-color: #4f5051; }
            QPushButton:disabled { background-color: #242526; color: #737475; }
            QPushButton#backup_button { background-color: #27ae60; color: white; }
            QPushButton#backup_button:hover { background-color: #229954; }
            QPushButton#restore_button { background-color: #fa383e; color: white; }
            QPushButton#restore_button:hover { background-color: #c0392b; }
            QPushButton#manage_button { background-color: #2d88ff; color: white; }
            QPushButton#manage_button:hover { background-color: #1d69d4; }
            QPushButton#save_needed_button { background-color: #27ae60; color: white; }
            QPushButton#save_needed_button:hover { background-color: #229954; }
            QProgressBar { border: 1px solid #3a3b3c; border-radius: 6px; text-align: center; color: #e4e6eb; }
            QProgressBar::chunk { background-color: #2d88ff; border-radius: 6px; }
            QLabel#header { font-size: 12pt; font-weight: bold; color: #e4e6eb; }
            QLabel#version_ok { background-color: #2c3e30; color: #27ae60; border: 1px solid #27ae60; border-radius: 6px; padding: 8px; }
            QLabel#version_update { background-color: #4d3c1a; color: #f39c12; border: 1px solid #f39c12; border-radius: 6px; padding: 8px; }
            QFrame#separator { background-color: #3a3b3c; }
            QListWidget { border: 1px solid #3a3b3c; border-radius: 6px; background-color: #242526; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #3a3b3c; }
            QListWidget::item:last-child { border-bottom: none; }
            QGroupBox { border: 1px solid #3a3b3c; border-radius: 6px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        """

def get_system_theme():
    if sys.platform == 'win32':
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REG_KEY)
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return 'light' if value == 1 else 'dark'
        except Exception: return 'dark'
    return 'dark'
