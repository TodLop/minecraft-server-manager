import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import STATIC_DIR, ENV_FILE, TEMPLATES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup/shutdown"""
    # Startup
    from app.services import minecraft_server
    from app.services import reboot_scheduler

    if await minecraft_server.ensure_log_tailer_running():
        print("✅ Minecraft server detected, log tailer started")
    else:
        print("ℹ️  Minecraft server not running")

    # Start reboot scheduler
    await reboot_scheduler.start_scheduler()
    print("✅ Reboot scheduler started")

    yield  # App runs here

    # Shutdown
    await reboot_scheduler.stop_scheduler()
    print("👋 App shutting down")


def create_app():
    """
    FastAPI application factory.
    Minecraft Server Management System
    """
    # Load environment variables
    load_dotenv(dotenv_path=ENV_FILE)

    # Require SECRET_KEY for session security
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise ValueError("ERROR: SECRET_KEY is missing in .env file!")

    # Create app instance
    app = FastAPI(
        title="Minecraft Server Manager",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan
    )

    # Templates for error pages
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Custom 404 exception handler
    @app.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        accept_header = request.headers.get("accept", "")
        is_browser_request = "text/html" in accept_header

        if exc.status_code == 404 and is_browser_request:
            return templates.TemplateResponse(
                "error.html",
                {"request": request},
                status_code=404
            )

        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    # Middleware
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure for your domain
    )

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        print(f"⚠️ Warning: Static directory not found at {STATIC_DIR}")

    # Router Registration (Minecraft management only)
    from app.routers import minecraft, admin, staff, plugin_docs

    # Admin Panel (restricted to ADMIN_EMAILS)
    app.include_router(admin.router, tags=["Admin"])

    # Staff Panel (restricted to STAFF_EMAILS + ADMIN_EMAILS)
    app.include_router(staff.router, tags=["Staff"])

    # Plugin Documentation (shared by staff + admins)
    app.include_router(plugin_docs.router, tags=["PluginDocs"])

    # Minecraft Wrapped (player stats pages)
    app.include_router(minecraft.router, tags=["Minecraft"])

    return app
