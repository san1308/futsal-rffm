"""Correcciones manuales de mis estadísticas, guardadas por partido en un JSON.

El acta de la RFFM no siempre refleja lo que pasó (goles mal asignados, no apuntan
asistencias, no saben quién estuvo en la portería…). Lo que edites aquí manda sobre el acta.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

# Campos editables de un partido y cómo se validan
BOOL_FIELDS = ("called", "starter", "goalkeeper")
INT_FIELDS = ("goals", "assists", "yellow", "red")
NULLABLE_INT_FIELDS = ("conceded",)
FIELDS = BOOL_FIELDS + INT_FIELDS + NULLABLE_INT_FIELDS


def clean(data: dict[str, Any]) -> dict[str, Any]:
    """Valida un parche; lanza ValueError con un mensaje legible si algo no cuadra."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k not in FIELDS:
            raise ValueError(f"Campo desconocido: {k}")
        if k in BOOL_FIELDS:
            if not isinstance(v, bool):
                raise ValueError(f"{k} tiene que ser sí o no")
        elif v is None and k in NULLABLE_INT_FIELDS:
            pass
        elif isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 99:
            raise ValueError(f"{k} tiene que ser un número entre 0 y 99")
        out[k] = v
    return out


class StatsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".stats-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def for_player(self, player_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            return self._read().get(player_id, {})

    def set(self, player_id: str, match_id: str, values: dict[str, Any]) -> dict[str, Any]:
        values = clean(values)
        with self._lock:
            data = self._read()
            data.setdefault(player_id, {})[match_id] = values
            self._write(data)
        return values

    def delete(self, player_id: str, match_id: str) -> None:
        with self._lock:
            data = self._read()
            if data.get(player_id, {}).pop(match_id, None) is not None:
                self._write(data)
