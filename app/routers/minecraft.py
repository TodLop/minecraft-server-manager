# app/routers/minecraft.py
"""
Minecraft Wrapped Routes for Near Outpost Server.
Handles player statistics pages for the Minecraft 2025 Wrapped feature.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.core.config import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Valid player names with their template files
VALID_PLAYERS = {
    "sparkleunit": "minecraft/sparkleunit.html",
    "chance_07": "minecraft/chance_07.html",
    "xX6manyangXx": "minecraft/xX6manyangXx.html",
    "sooroh": "minecraft/sooroh.html",
    "hjjang17": "minecraft/hjjang17.html",
    "aruvn001": "minecraft/aruvn001.html",
    "meloeyxi": "minecraft/meloeyxi.html",
}


# --- Dynamic Wrapped Route (for nearoutpost-web.hjjang.dev/wrapped/{player}) ---

@router.get("/wrapped/{player}", response_class=HTMLResponse)
async def wrapped_player_dynamic(player: str, request: Request):
    """
    Dynamic route for player wrapped pages.
    Used on nearoutpost-web.hjjang.dev subdomain.
    """
    if player not in VALID_PLAYERS:
        raise HTTPException(status_code=404, detail=f"Player '{player}' not found")

    return templates.TemplateResponse(VALID_PLAYERS[player], {"request": request})


# --- Legacy Routes (for backward compatibility on main domain) ---
# These redirect to the subdomain wrapped URLs

@router.get("/sparkleunit", response_class=HTMLResponse)
async def wrapped_sparkleunit(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/sparkleunit.html", {"request": request})

@router.get("/chance_07", response_class=HTMLResponse)
async def wrapped_chance_07(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/chance_07.html", {"request": request})

@router.get("/xX6manyangXx", response_class=HTMLResponse)
async def wrapped_xX6manyangXx(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/xX6manyangXx.html", {"request": request})

@router.get("/sooroh", response_class=HTMLResponse)
async def wrapped_sooroh(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/sooroh.html", {"request": request})

@router.get("/hjjang17", response_class=HTMLResponse)
async def wrapped_hjjang17(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/hjjang17.html", {"request": request})

@router.get("/aruvn001", response_class=HTMLResponse)
async def wrapped_aruvn001(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/aruvn001.html", {"request": request})

@router.get("/meloeyxi", response_class=HTMLResponse)
async def wrapped_meloeyxi(request: Request):
    """Legacy route - serves directly for now"""
    return templates.TemplateResponse("minecraft/meloeyxi.html", {"request": request})

