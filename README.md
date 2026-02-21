# Minecraft Server Manager

Open-source FastAPI + Bukkit tooling for operating a Minecraft Paper server.

KR: 이 저장소는 마인크래프트 서버 운영 기능만 포함한 공개용 레포입니다.

## What This Project Is

This repository provides a focused operations stack for a single Minecraft environment:
- web-based admin/staff dashboards
- server lifecycle control (start/stop/restart/recover)
- scheduler automation (reboot + backup)
- moderation and investigation workflows
- RBAC and owner-governed staff tiering
- plugin documentation and update workflows

Non-Minecraft modules were intentionally excluded.

## Core Capabilities

- **Server control and observability**
  - Start/stop/restart via operations contract
  - RCON command execution with policy/rate limiting
  - Live console/log views + raw log endpoints
  - Health-aware status fields: `running`, `process_running`, `healthy`, `state_reason`

- **Reliability operations**
  - Emergency recovery endpoint for desynced UI/process states:
    - `POST /minecraft/admin/api/minecraft/server/recover`
  - Idempotent operation handling and operation-state history

- **Role and permission model**
  - Staff RBAC presets + per-user `grant/revoke`
  - Minecraft-local owner/manager-admin tier governance
  - Owner-only promotion/demotion/audit views for manager-admin lifecycle

- **Automation**
  - Reboot scheduler
  - Backup scheduler

- **Moderation and staff tooling**
  - Kick/tempban/broadcast
  - Warnings/watchlist/notes
  - Investigation and spectator workflows

- **Plugin operations**
  - Plugin documentation portal
  - Update checks and update-with-restart flow

- **Backend operations docs**
  - Internal operations documentation routes under `/minecraft/backend-docs`
  - Staff access requires `ops:backend_docs:view`

- **Optional analytics**
  - Admin analytics routes and WebSocket metrics stream
  - Loaded as optional module (fails closed if dependency import fails)

## Architecture At a Glance

```text
app/
  core/
    auth.py                # global auth/session helpers
    config.py              # env-driven config and paths
    minecraft_access.py    # Minecraft-local admin/owner dependencies

  routers/
    admin.py               # admin aggregator + dashboard
    admin_server.py        # server control/logs/updates/recover
    admin_scheduler.py     # scheduler APIs
    admin_moderation.py    # moderation admin APIs
    admin_rbac.py          # RBAC + owner/manager-admin governance
    admin_analytics.py     # optional analytics routes
    staff.py               # staff dashboard + moderated operations
    plugin_docs.py         # plugin docs APIs/pages
    backend_docs.py        # backend-docs APIs/pages

  services/
    minecraft_server.py        # process + readiness + recovery
    operations.py              # operation registry/idempotency
    reboot_scheduler.py        # automated reboot logic
    backup_scheduler.py        # backup automation
    permissions.py             # RBAC model and presets
    minecraft_admin_tiers.py   # owner/manager-admin lifecycle
    user_preferences.py        # per-user UI preferences
    backend_docs.py            # markdown-backed ops docs
    metrics_db.py              # optional analytics storage
    server_metrics.py          # optional metrics collector
```

## Access Model

Minecraft module access is layered and explicit:

- **owner**
  - Full Minecraft admin access
  - Owner-only governance endpoints:
    - `GET /minecraft/admin/api/minecraft/admin-tiers/overview`
    - `POST /minecraft/admin/api/minecraft/admin-tiers/promote/{email}`
    - `POST /minecraft/admin/api/minecraft/admin-tiers/demote/{email}`
    - `GET /minecraft/admin/api/minecraft/admin-audit/logs`

- **manager_admin**
  - Minecraft admin access
  - Can manage RBAC for **staff subjects only**
  - Cannot mutate owner/other manager-admin subjects

- **staff**
  - Access is permission-based via RBAC presets and per-user overrides
  - Effective permissions formula:
    - `(role_permissions union grants) minus revokes`

- **external**
  - No staff/admin access

KR: 오너/매니저/스태프 권한은 마인크래프트 모듈 내부 로직으로 분리되어 동작합니다.

## Reliability and Recovery

`recover` exists for incidents where UI state and real server state diverge.

Current recovery flow (`minecraft_server.recover_server`):
1. Precheck current health/state reason.
2. If process exists, force-stop safely.
3. Clean stale PID if detected.
4. Start/restart with readiness checks.
5. Postcheck and return structured step-by-step result.

Common state reasons include:
- `ok`
- `stale_pid`
- `process_no_port`
- `port_busy_no_process`
- `starting`
- `stopped`

## Privacy and Data Hygiene

This repository is sanitized for open-source publication:

- Runtime and sensitive paths are excluded:
  - `.env`
  - `config_files/`
  - `data/`
  - `logs/`
- Secret-like artifacts are not committed:
  - credentials/tokens/private keys
- Plugin build/IDE artifacts are excluded:
  - `custom_plugins/**/target/`, `*.jar`, `*.class`, `.project`, `.classpath`, `.settings/`
- Configuration is environment-variable driven (see `.env.example`)

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

Optional dev/test dependencies:

```bash
pip install -r requirements-dev.txt
```

### 2) Configure environment

```bash
cp .env.example .env
```

Minimum values to set:
- `SECRET_KEY`
- `ADMIN_EMAILS`
- `STAFF_EMAILS`
- `MINECRAFT_SERVER_PATH`

### 3) Run

```bash
python run.py
```

Default local URL: `http://127.0.0.1:8000`

## Testing

Example test run:

```bash
SECRET_KEY=test-secret ADMIN_EMAILS=admin@example.com STAFF_EMAILS=staff@example.com pytest -q
```

Note:
- Some optional analytics paths may require additional runtime dependency (`psutil`).

## Demo Scope

This repository is maintained as the core Minecraft manager codebase.
Website/landing-page presentation assets should be treated as external demo context, not core product scope.

## License

MIT
