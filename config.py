import sys
from pathlib import Path

# --- CONFIGURATION ---
APP_NAME = "ImmichSafe"
APP_VERSION = "3.0.0"
CONFIG_FILE = Path.home() / f".{APP_NAME.lower()}_config.json"
VERSIONS_CACHE_FILE = Path.home() / f".{APP_NAME.lower()}_versions_cache.json"
REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
THEME_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

IS_WINDOWS = sys.platform == 'win32'