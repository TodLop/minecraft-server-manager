import os
from pathlib import Path

import yaml

# ==========================================
# Path Configuration
# ==========================================

CORE_DIR = Path(__file__).resolve().parent
APP_DIR = CORE_DIR.parent
ROOT_DIR = APP_DIR.parent

CONFIG_FILES_DIR = ROOT_DIR / "config_files"
TOKEN_FILE = CONFIG_FILES_DIR / "token.json"
CREDS_FILE = CONFIG_FILES_DIR / "credentials.json"
CLIENT_SECRETS_FILE = CONFIG_FILES_DIR / "client_secret_web.json"
ENV_FILE = ROOT_DIR / ".env"

STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
HISTORY_DIR = DATA_DIR / "history"
TASKBOARD_IMAGES_DIR = DATA_DIR / "taskboard_images"
BACKUP_TEMP_DIR = DATA_DIR / "backup_temp"
METRICS_DB_PATH = DATA_DIR / "server_metrics.db"

# ==========================================
# Minecraft Server Configuration
# ==========================================

_raw_mc_path = os.getenv("MINECRAFT_SERVER_PATH", str(DATA_DIR / "minecraft_server_paper")).strip()
MINECRAFT_SERVER_PATH = Path(_raw_mc_path).expanduser()
if not MINECRAFT_SERVER_PATH.is_absolute():
    MINECRAFT_SERVER_PATH = ROOT_DIR / MINECRAFT_SERVER_PATH

_staff_emails = os.getenv("STAFF_EMAILS", "staff@example.com")
STAFF_EMAILS = frozenset(
    email.strip().lower() for email in _staff_emails.split(",") if email.strip()
)


def load_protected_players() -> frozenset[str]:
    """Load protected players list from YAML config file."""
    config_file = DATA_DIR / "protected_players.yml"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                players = data.get("protected_players", []) if data else []
                normalized = [str(p).strip() for p in players if str(p).strip()]
                if normalized:
                    return frozenset(normalized)
        except Exception:
            pass
    return frozenset(["admin_player"])


PROTECTED_PLAYERS = load_protected_players()

# ==========================================
# App Configuration
# ==========================================

APP_VERSION = os.getenv("APP_VERSION", "1.1.0")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
API_BASE_URL = f"http://{HOST}:{PORT}"

# OAuth scopes for Google sign-in
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
