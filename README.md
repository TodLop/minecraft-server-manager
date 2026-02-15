# Minecraft Server Manager

Open-source FastAPI + Bukkit tooling for operating a Minecraft Paper server.

## Scope
This repository is focused on Minecraft server operations only:
- server start/stop/restart and RCON command execution
- live console/log access
- reboot scheduler and backup scheduler
- admin/staff RBAC controls
- plugin update checks (Paper + Modrinth)
- moderation workflows and plugin documentation

Non-Minecraft product modules were intentionally excluded from this repository.

## Privacy and Data Hygiene
This repository is sanitized for open-source use.
- Runtime data is excluded (`data/`, `logs/`, `config_files/`, `.env`)
- Secrets and personal credentials are not committed
- Configuration is environment-variable driven

## Project Layout
```text
minecraft-server-manager/
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── config.py
│   │   └── auth.py
│   ├── routers/
│   │   ├── admin.py
│   │   ├── admin_server.py
│   │   ├── admin_scheduler.py
│   │   ├── admin_moderation.py
│   │   ├── admin_rbac.py
│   │   ├── staff.py
│   │   └── plugin_docs.py
│   ├── services/
│   │   ├── minecraft_server.py
│   │   ├── rcon.py
│   │   ├── operations.py
│   │   ├── reboot_scheduler.py
│   │   ├── backup_scheduler.py
│   │   └── ...
│   ├── templates/
│   └── static/
├── custom_plugins/
│   ├── MoneyHistory/
│   ├── ServerShop/
│   ├── CORASpectator/
│   └── ServerAccount/
├── run.py
└── requirements.txt
```

## Quick Start
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
```

3. Run:
```bash
python run.py
```

## License
MIT
