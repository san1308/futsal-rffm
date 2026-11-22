"""API propia + frontend estático."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .cache import cache
from .config import settings
from .rffm import DemoClient, RFFMClient, RFFMError
from .service import Service
from .store import StatsStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = DemoClient() if settings.demo else RFFMClient()
    app.state.service = Service(client, StatsStore(settings.stats_file))
    yield
    await client.aclose()


app = FastAPI(title="Futsal RFFM", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


def svc() -> Service:
    return app.state.service


@app.exception_handler(httpx.HTTPError)
async def rffm_down(_, exc: httpx.HTTPError):
    return JSONResponse({"detail": "La web de la RFFM no responde ahora mismo."}, status_code=502)


@app.exception_handler(RFFMError)
async def rffm_bad(_, exc: RFFMError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.get("/api/health")
async def health():
    return {"ok": True, "demo": settings.demo}


@app.get("/api/config")
async def config():
    return {"myTeam": settings.mi_equipo, "myPlayer": settings.mi_jugador or None, "demo": settings.demo,
            "editable": True, "needsKey": bool(settings.edit_key)}


@app.get("/api/calendar")
async def calendar():
    return await svc().calendar()


@app.get("/api/standings")
async def standings(round: int | None = None):
    return await svc().standings(round)


@app.get("/api/scorers")
async def scorers():
    return await svc().scorers()


@app.get("/api/match/{codacta}")
async def match(codacta: str):
    if not codacta.isdigit():
        raise HTTPException(400, "Código de acta no válido")
    return await svc().match(codacta)


@app.get("/api/team/{team_id}")
async def team(team_id: str):
    try:
        return await svc().team(team_id)
    except KeyError:
        raise HTTPException(404, "Ese equipo no está en el grupo")


@app.get("/api/me")
async def me():
    if not settings.mi_jugador:
        raise HTTPException(404, "MI_JUGADOR no configurado")
    return await svc().player(settings.mi_jugador, settings.mi_equipo)


def _check_key(key: str | None) -> str:
    if not settings.mi_jugador:
        raise HTTPException(404, "MI_JUGADOR no configurado")
    if settings.edit_key and (not key or not hmac.compare_digest(key.encode(), settings.edit_key.encode())):
        raise HTTPException(401, "Clave de edición incorrecta")
    return settings.mi_jugador


@app.post("/api/me/check")
async def me_check(x_edit_key: str | None = Header(default=None)):
    _check_key(x_edit_key)
    return {"ok": True}


@app.put("/api/me/games/{match_id}")
async def me_edit(match_id: str, body: dict, x_edit_key: str | None = Header(default=None)):
    """Guarda mis números reales de un partido (sustituyen a los del acta)."""
    player = _check_key(x_edit_key)
    if not match_id.isdigit():
        raise HTTPException(400, "Código de acta no válido")
    try:
        saved = svc().store.set(player, match_id, body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "saved": saved}


@app.delete("/api/me/games/{match_id}")
async def me_reset(match_id: str, x_edit_key: str | None = Header(default=None)):
    """Vuelve a lo que diga el acta para ese partido."""
    svc().store.delete(_check_key(x_edit_key), match_id)
    return {"ok": True}


@app.post("/api/refresh")
async def refresh():
    """Vacía la caché (útil justo después de un partido)."""
    cache.clear()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
async def sw():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    return FileResponse(STATIC / "index.html")
