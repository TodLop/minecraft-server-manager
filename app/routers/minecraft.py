# app/routers/minecraft.py
"""
Minecraft Wrapped Routes.
Handles player statistics pages for the Minecraft Wrapped feature.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Valid player names with their template files (demo examples)
VALID_PLAYERS = {
    "sparkleunit": "minecraft/sparkleunit.html",
    "hjjang17": "minecraft/hjjang17.html",
}


@router.get("/wrapped/{player}", response_class=HTMLResponse)
async def wrapped_player_dynamic(player: str, request: Request):
    """Dynamic route for player wrapped pages."""
    if player not in VALID_PLAYERS:
        raise HTTPException(status_code=404, detail=f"Player '{player}' not found")

    return templates.TemplateResponse(VALID_PLAYERS[player], {"request": request})


@router.get("/sparkleunit", response_class=HTMLResponse)
async def wrapped_sparkleunit(request: Request):
    """Demo player wrapped page"""
    return templates.TemplateResponse("minecraft/sparkleunit.html", {"request": request})

@router.get("/hjjang17", response_class=HTMLResponse)
async def wrapped_hjjang17(request: Request):
    """Demo player wrapped page"""
    return templates.TemplateResponse("minecraft/hjjang17.html", {"request": request})
