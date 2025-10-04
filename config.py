import sys
from pathlib import Path

# --- CONFIGURATION ---
APP_NAME = "ImmichSafe"
APP_VERSION = "3.1.0"
CONFIG_FILE = Path.home() / f".{APP_NAME.lower()}_config.json"

# --- Platform Detection ---
IS_WINDOWS = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
IS_LINUX = not IS_WINDOWS and not IS_MAC

# --- Platform-Specific Paths ---

# Windows-specific registry paths
if IS_WINDOWS:
    REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    THEME_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# Linux-specific autostart path
if IS_LINUX:
    AUTOSTART_DIR_LINUX = Path.home() / ".config" / "autostart"

# macOS-specific Launch Agent path
if IS_MAC:
    LAUNCH_AGENTS_DIR_MAC = Path.home() / "Library" / "LaunchAgents"

