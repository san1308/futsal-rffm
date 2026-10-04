"""Caché en memoria con TTL.

Si la RFFM falla, se devuelve el último valor bueno aunque haya caducado
(mejor un dato de hace 15 minutos que una pantalla de error en el pabellón).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[Any]],
        ttl: int | Callable[[Any], int],
    ) -> Any:
        hit = self._data.get(key)
        if hit and hit[0] > time.time():
            return hit[1]

        # Un único fetch por clave aunque lleguen varias peticiones a la vez
        async with self._lock(key):
            hit = self._data.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
            try:
                value = await fetch()
            except Exception:
                if hit:
                    log.warning("RFFM no responde para %s, sirvo dato antiguo", key, exc_info=True)
                    return hit[1]
                raise
            seconds = ttl(value) if callable(ttl) else ttl
            self._data[key] = (time.time() + seconds, value)
            return value

    def clear(self) -> None:
        self._data.clear()


cache = TTLCache()
