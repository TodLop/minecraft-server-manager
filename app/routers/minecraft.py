"""Optional Minecraft Wrapped routes (disabled by default via ENABLE_WRAPPED_PAGES=false)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

VALID_PLAYERS = {
    "player_one": "minecraft/player_one.html",
    "admin_player": "minecraft/admin_player.html",
}


@router.get("/wrapped/{player}", response_class=HTMLResponse)
async def wrapped_player_dynamic(player: str, request: Request):
    """Dynamic route for wrapped pages."""
    if player not in VALID_PLAYERS:
        raise HTTPException(status_code=404, detail=f"Player '{player}' not found")

    return templates.TemplateResponse(VALID_PLAYERS[player], {"request": request})


@router.get("/player_one", response_class=HTMLResponse)
async def wrapped_player_one(request: Request):
    """Legacy demo route."""
    return templates.TemplateResponse("minecraft/player_one.html", {"request": request})


@router.get("/admin_player", response_class=HTMLResponse)
async def wrapped_admin_player(request: Request):
    """Legacy demo route."""
    return templates.TemplateResponse("minecraft/admin_player.html", {"request": request})
