# app/core/config.py
import os
from pathlib import Path

import yaml

# ==========================================
# 📂 PATH CONFIGURATION
# ==========================================

CORE_DIR = Path(__file__).resolve().parent
APP_DIR = CORE_DIR.parent
ROOT_DIR = APP_DIR.parent

# OAuth credentials directory
CONFIG_FILES_DIR = ROOT_DIR / 'config_files'
CLIENT_SECRETS_FILE = CONFIG_FILES_DIR / 'client_secret_web.json'

# Environment variables file
ENV_FILE = ROOT_DIR / '.env'

# App resource paths
STATIC_DIR = APP_DIR / 'static'
TEMPLATES_DIR = APP_DIR / 'templates'

# Data storage paths
DATA_DIR = ROOT_DIR / 'data'

# ==========================================
# 🎮 MINECRAFT SERVER CONFIGURATION
# ==========================================

# Change folder name here when switching servers
MINECRAFT_SERVER_PATH = DATA_DIR / "minecraft_server_paper"

# Staff emails - loaded from environment variable
# Set STAFF_EMAILS in .env as comma-separated emails
_staff_emails_str = os.getenv("STAFF_EMAILS", "")
STAFF_EMAILS = frozenset(
    email.strip() for email in _staff_emails_str.split(",") if email.strip()
)

# Load protected players from YAML config (editable at runtime)
def load_protected_players():
    """Load protected players list from YAML config file."""
    config_file = DATA_DIR / "protected_players.yml"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
                players = data.get("protected_players", []) if data else []
                return frozenset(players) if players else frozenset(["admin_player"])
        except Exception:
            pass
    return frozenset(["admin_player"])  # Fallback default

# Players that cannot be banned by staff (admin protection)
PROTECTED_PLAYERS = load_protected_players()


# ==========================================
# ⚙️ SERVER CONFIGURATION
# ==========================================

PORT = int(os.getenv("PORT", 8000))
HOST = "127.0.0.1"
API_BASE_URL = f"http://{HOST}:{PORT}"


# ==========================================
# 🔐 GOOGLE OAUTH SCOPES (for admin authentication)
# ==========================================
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
