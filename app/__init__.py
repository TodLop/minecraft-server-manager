import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import APP_VERSION, ENV_FILE, STATIC_DIR, TEMPLATES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup/shutdown."""
    from app.services import backup_scheduler, minecraft_server, reboot_scheduler

    if await minecraft_server.ensure_log_tailer_running():
        print("Minecraft server detected, log tailer started")
    else:
        print("Minecraft server not running")

    await reboot_scheduler.start_scheduler()
    print("Reboot scheduler started")

    await backup_scheduler.start_scheduler()
    print("Backup scheduler started")

    try:
        from app.services import permissions as permissions_service

        permissions_service.migrate_from_v1()
    except Exception:
        pass

    yield

    await backup_scheduler.stop_scheduler()
    await reboot_scheduler.stop_scheduler()
    print("App shutting down")


def create_app():
    """FastAPI application factory."""
    load_dotenv(dotenv_path=ENV_FILE)

    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise ValueError("ERROR: SECRET_KEY is missing in .env file!")

    app = FastAPI(
        title="Minecraft Server Manager",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        accept_header = request.headers.get("accept", "")
        is_browser_request = "text/html" in accept_header

        if exc.status_code == 404 and is_browser_request:
            return templates.TemplateResponse(
                "error.html",
                {"request": request},
                status_code=404,
            )

        if exc.status_code == 403 and is_browser_request and request.url.path.startswith("/minecraft/plugins"):
            return templates.TemplateResponse(
                "plugins/access_denied.html",
                {
                    "request": request,
                    "user_info": request.state.user if hasattr(request.state, "user") else {},
                },
                status_code=403,
            )

        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        print(f"Warning: Static directory not found at {STATIC_DIR}")

    from app.routers import admin, backend_docs, plugin_docs, staff

    app.include_router(admin.router, tags=["Admin"])
    app.include_router(backend_docs.router, tags=["BackendDocs"])
    app.include_router(staff.router, tags=["Staff"])
    app.include_router(plugin_docs.router, tags=["PluginDocs"])

    enable_wrapped = os.getenv("ENABLE_WRAPPED_PAGES", "false").lower() in {"1", "true", "yes"}
    if enable_wrapped:
        from app.routers import minecraft

        app.include_router(minecraft.router, tags=["Minecraft"])

    return app
