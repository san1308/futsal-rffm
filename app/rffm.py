"""Cliente de la web de la RFFM (www.rffm.es).

La web es una app Next.js. Hay dos fuentes de datos:
  * API interna JSON:  /api/standings, /api/scorers, /api/group-rounds
  * Páginas renderizadas en servidor, cuyos datos van en <script id="__NEXT_DATA__">:
      /competicion/calendario   -> pageProps.calendar  (todas las jornadas con resultados)
      /acta-partido/{codacta}   -> pageProps.game      (alineaciones, goles, tarjetas, árbitros)

Aquí solo se descarga y se devuelve el JSON crudo; la normalización está en service.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from .config import settings

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S
)
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


class RFFMError(RuntimeError):
    pass


def extract_next_data(html: str) -> dict[str, Any]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise RFFMError("La página de la RFFM no trae __NEXT_DATA__ (¿han cambiado la web?)")
    return json.loads(m.group(1))


class RFFMClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) futsal-rffm/1.0 (uso personal)",
                "Accept-Language": "es-ES,es;q=0.9",
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("estado") not in (None, "1"):
            raise RFFMError(f"La RFFM devolvió estado={data.get('estado')} en {path}")
        return data

    async def _page_props(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return extract_next_data(r.text)["props"]["pageProps"]

    # --- Endpoints -------------------------------------------------------

    async def calendar(self) -> dict[str, Any]:
        props = await self._page_props(
            "/competicion/calendario",
            {
                "temporada": settings.temporada,
                "tipojuego": settings.tipojuego,
                "competicion": settings.competicion,
                "grupo": settings.grupo,
            },
        )
        cal = props.get("calendar")
        if not cal or "rounds" not in cal:
            raise RFFMError("Calendario vacío")
        cal["currentRound"] = props.get("currentRound")
        return cal

    async def standings(self, round_: str) -> dict[str, Any]:
        return await self._json("/api/standings", {"idGroup": settings.grupo, "round": round_})

    async def scorers(self) -> dict[str, Any]:
        return await self._json(
            "/api/scorers", {"idGroup": settings.grupo, "idCompetition": settings.competicion}
        )

    async def acta(self, codacta: str) -> dict[str, Any]:
        props = await self._page_props(
            f"/acta-partido/{codacta}",
            {"temporada": settings.temporada, "competicion": settings.competicion, "grupo": settings.grupo},
        )
        game = props.get("game")
        if not game:
            raise RFFMError(f"Acta {codacta} sin datos")
        return game


class DemoClient:
    """Sirve datos reales guardados en tests/fixtures (para desarrollar sin red)."""

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    async def aclose(self) -> None:  # pragma: no cover
        pass

    async def calendar(self) -> dict[str, Any]:
        return self._load("calendar.json")

    async def standings(self, round_: str) -> dict[str, Any]:
        return self._load("standings.json")

    async def scorers(self) -> dict[str, Any]:
        return self._load("scorers.json")

    async def acta(self, codacta: str) -> dict[str, Any]:
        path = FIXTURES / f"acta_{codacta}.json"
        if not path.exists():
            raise RFFMError(f"No hay acta {codacta} en modo demo")
        return json.loads(path.read_text(encoding="utf-8"))
