# Minecraft Server Manager

A full-stack web application for managing a Minecraft Paper server. Built with **FastAPI** (Python) and custom **Bukkit plugins** (Java), this system provides real-time server control, automated updates, player moderation, and analytics — all through a role-based admin/staff dashboard.

> **Production system** — actively managing a Minecraft server at [hjjang.dev](https://hjjang.dev)

---

## Features

### Server Control & Monitoring
- **Real-time console** — WebSocket-powered live log streaming with command execution via RCON
- **One-click server management** — Start, stop, and restart the Minecraft process directly from the dashboard
- **Automated reboot scheduler** — State machine (monitoring → countdown → restarting) with configurable schedules and player notifications
- **Server status API** — Live player count, TPS, memory usage, and uptime

### Automated Update System
- **PaperMC auto-updater** — Detects new Paper builds via the PaperMC API, downloads, and applies updates
- **Modrinth plugin updater** — Checks all installed plugins against Modrinth's API for version updates, with one-click install
- **Plugin notification system** — Tracks available updates and notifies admins

### Player Moderation
- **Ban/Kick/Mute controls** — Execute moderation commands with audit logging
- **Player watchlist** — Track suspicious players with notes and severity levels
- **Warning system** — Issue, track, and escalate player warnings
- **Protected players** — Configurable list of players that staff cannot ban (admin protection)
- **CoreProtect integration** — Query block/container history for grief investigation with visual timeline
- **GrimAC integration** — Anti-cheat violation tracking and analysis from SQLite databases

### Spectator System
- **Spectator session management** — Staff can request spectator mode sessions with admin approval workflow
- **Session tracking** — Time-limited spectator access with automatic expiration

### Staff Dashboard
- **Role-based access control** — Separate Admin and Staff permission tiers via Google OAuth
- **Investigation tools** — Dedicated interface for grief/cheat investigation with CoreProtect + GrimAC data
- **Player notes** — Persistent notes system for staff coordination
- **Staff settings** — Per-user preferences and dashboard configuration

### Minecraft Wrapped
- **Player statistics pages** — Animated, React-based "year in review" pages for players (see [demo examples](app/templates/minecraft/))

### Custom Bukkit Plugins (Java)
- **ServerShop** — In-game economy shop with tiered pricing, leaderboards, and LuckPerms integration
- **MoneyHistory** — Transaction logging plugin for the server economy
- **CORASpectator** — Server-side spectator session management companion plugin

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.13, FastAPI, Uvicorn |
| **Frontend** | Jinja2 templates, Tailwind CSS, vanilla JS, React (Wrapped pages) |
| **Real-time** | WebSockets (log streaming), Server-Sent Events |
| **Database** | SQLAlchemy + SQLite (CoreProtect, GrimAC) |
| **Auth** | Google OAuth 2.0, session-based with role hierarchy |
| **Minecraft** | RCON protocol client, PaperMC API, Modrinth API |
| **Plugins** | Java 17, Bukkit/Paper API, Maven |
| **Scheduling** | asyncio-based state machine for reboot scheduling |

---

## Architecture

```
minecraft-server-manager/
├── app/
│   ├── __init__.py              # FastAPI app factory with lifespan events
│   ├── core/
│   │   ├── config.py            # Centralized path & environment config
│   │   └── auth.py              # Role-based auth (Admin/Staff/User)
│   ├── routers/
│   │   ├── admin.py             # Admin panel — full server control (2100+ lines)
│   │   ├── staff.py             # Staff panel — limited moderation tools
│   │   ├── minecraft.py         # Player Wrapped statistics pages
│   │   └── plugin_docs.py       # Plugin documentation CRUD system
│   ├── services/
│   │   ├── minecraft_server.py  # RCON client, process management, log streaming
│   │   ├── minecraft_updater.py # PaperMC & Modrinth update automation
│   │   ├── reboot_scheduler.py  # Auto-restart state machine
│   │   ├── coreprotect.py       # Grief investigation queries
│   │   ├── grimac.py            # Anti-cheat violation tracking
│   │   ├── investigation.py     # Investigation session management
│   │   ├── spectator_session.py # Spectator approval workflow
│   │   └── ...                  # warnings, watchlist, player_notes, etc.
│   ├── templates/               # Jinja2 HTML templates
│   └── static/                  # CSS, JS, images
├── custom_plugins/
│   ├── ServerShop/              # Economy shop plugin (Java/Maven)
│   ├── MoneyHistory/            # Transaction logging plugin
│   └── CORASpectator/           # Spectator management plugin
├── run.py                       # Server entry point
└── requirements.txt
```

---

## Code Highlights

### RCON Protocol Client
The server communicates with Minecraft through a custom async RCON client that handles packet framing, authentication, and response fragmentation — see [`minecraft_server.py`](app/services/minecraft_server.py).

### Reboot Scheduler State Machine
The auto-restart system uses a clean state machine pattern (`monitoring → countdown → restarting → monitoring`) with player warnings at configurable intervals — see [`reboot_scheduler.py`](app/services/reboot_scheduler.py).

### PaperMC + Modrinth Update Automation
Automatically checks for new Paper server builds and plugin updates across Modrinth's API, with hash verification and rollback support — see [`minecraft_updater.py`](app/services/minecraft_updater.py).

### CoreProtect Grief Investigation
Queries CoreProtect's SQLite database directly to build visual timelines of block changes, helping staff investigate griefing incidents — see [`coreprotect.py`](app/services/coreprotect.py).

---

## Setup

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/TodLop/minecraft-server-manager.git
   cd minecraft-server-manager
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your SECRET_KEY, ADMIN_EMAILS, etc.
   ```

3. **Set up Google OAuth** (for admin authentication):
   - Create OAuth credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   - Download `client_secret_web.json` to `config_files/`

4. **Run:**
   ```bash
   python run.py
   ```

---

## License

[MIT](LICENSE)
