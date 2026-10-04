"""Configuración leída de variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    # Identificadores de la competición en la web de la RFFM (salen en la URL del calendario)
    temporada: str = _env("RFFM_TEMPORADA", "22")
    tipojuego: str = _env("RFFM_TIPOJUEGO", "3")
    competicion: str = _env("RFFM_COMPETICION", "26738221")
    grupo: str = _env("RFFM_GRUPO", "26771028")

    # Tu equipo y tú (códigos internos de la RFFM)
    mi_equipo: str = _env("MI_EQUIPO", "17146426")  # C.D.E. Casco Antiguo Carabanchel 'A'
    mi_jugador: str = _env("MI_JUGADOR", "2799670")  # vacío = ocultar "Mis números"

    base_url: str = _env("RFFM_BASE_URL", "https://www.rffm.es")
    img_host: str = _env("RFFM_IMG_HOST", "https://appweb.rffm.es")

    # Caché (segundos)
    ttl_calendario: int = int(_env("TTL_CALENDARIO", "600"))
    ttl_clasificacion: int = int(_env("TTL_CLASIFICACION", "600"))
    ttl_goleadores: int = int(_env("TTL_GOLEADORES", "1800"))
    ttl_acta_abierta: int = int(_env("TTL_ACTA_ABIERTA", "300"))
    ttl_acta_cerrada: int = int(_env("TTL_ACTA_CERRADA", "604800"))

    # Modo demo: sirve los datos guardados en tests/fixtures sin llamar a la RFFM
    demo: bool = _env("DEMO", "0") == "1"


settings = Settings()
