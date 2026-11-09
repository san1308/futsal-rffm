"""Normaliza los datos crudos de la RFFM a un formato limpio para el frontend."""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Any

from .cache import cache
from .config import settings

# --- Utilidades ----------------------------------------------------------

_PREFIXES = re.compile(
    r"^(?:(?:C\.?D\.?E\.?|C\.?D\.?B\.?|C\.?D\.?|C\.?F\.?S\.?|A\.?D\.?|F\.?S\.?|CLUB|AGRUPACION)\s+)+",
    re.I,
)
_SPONSOR = re.compile(r"\s*-\s+|\s+-\s*")  # guion con espacio a algún lado = patrocinador
_SUFFIX = re.compile(r"\s*'[A-Z]'\s*$|\s+[A-Z]$")
_LOWER = {"de", "del", "la", "las", "los", "y", "el"}


def short_name(name: str) -> str:
    """'C.D.E. CASCO ANTIGUO CARABANCHEL 'A'' -> 'Casco Antiguo Carabanchel'."""
    n = (name or "").strip()
    n = _SUFFIX.sub("", n)
    n = _SPONSOR.split(n)[0]
    n = _PREFIXES.sub("", n).strip(" .-")
    n = re.sub(r"\s+F\.?S\.?$", "", n).strip()
    words = n.lower().split()
    cap = lambda w: re.sub(r"(^|['\-])(\w)", lambda m: m.group(1) + m.group(2).upper(), w)
    out = [w if (i and w in _LOWER) else cap(w) for i, w in enumerate(words)]
    return " ".join(out) or name


def crest(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return settings.img_host.rstrip("/") + "/" + path.lstrip("/")


def _int(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _date(s: str | None) -> str | None:
    try:
        return datetime.strptime(s or "", "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


def team(id_: str, name: str, crest_path: str | None) -> dict[str, Any]:
    return {
        "id": id_,
        "name": (name or "").strip(),
        "short": short_name(name),
        "crest": crest(crest_path),
        "mine": id_ == settings.mi_equipo,
    }


# --- Calendario ----------------------------------------------------------

def normalize_match(raw: dict[str, Any], jornada: int) -> dict[str, Any]:
    gh, ga = _int(raw.get("goles_casa")), _int(raw.get("goles_visitante"))
    played = gh is not None and ga is not None
    return {
        "id": raw["codacta"],
        "jornada": jornada,
        "date": _date(raw.get("fecha")),
        "time": (raw.get("hora") or "").strip() or None,
        "venue": (raw.get("campo") or "").strip() or None,
        "home": team(raw["codigo_equipo_local"], raw["equipo_local"], raw.get("escudo_equipo_local")),
        "away": team(raw["codigo_equipo_visitante"], raw["equipo_visitante"], raw.get("escudo_equipo_visitante")),
        "score": {"home": gh, "away": ga} if played else None,
        "status": "played" if played else "scheduled",
    }


def _round_end(r: dict[str, Any]) -> str | None:
    """Último día de la semana de la jornada (los partidos aplazados a otra fecha no cuentan)."""
    if not r["date"]:
        return None
    start = date.fromisoformat(r["date"])
    week = [m["date"] for m in r["matches"]
            if m["date"] and abs((date.fromisoformat(m["date"]) - start).days) <= 6]
    return max([r["date"], *week])


def current_round(rounds: list[dict[str, Any]], today: date | None = None) -> int:
    """Jornada de esta semana: la primera que aún no ha terminado según el calendario.

    Los partidos que se quedaron sin jugar no la "atascan": al pasar el fin de semana
    de la jornada se salta a la siguiente. Sin fechas, la primera con partidos pendientes.
    """
    if not rounds:
        return 1
    today_s = (today or date.today()).isoformat()
    dated = [(r["number"], _round_end(r)) for r in rounds]
    if all(end for _, end in dated):
        upcoming = [n for n, end in dated if end >= today_s]
        return upcoming[0] if upcoming else rounds[-1]["number"]
    pending = [r["number"] for r in rounds if any(x["status"] == "scheduled" for x in r["matches"])]
    return min(pending) if pending else rounds[-1]["number"]


def normalize_calendar(raw: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    rounds = []
    for r in raw["rounds"]:
        n = _int(r.get("codjornada")) or len(rounds) + 1
        matches = [normalize_match(m, n) for m in r.get("equipos", [])]
        matches.sort(key=lambda m: (m["date"] or "9999", m["time"] or "99:99"))
        m = re.search(r"\((\d{2}-\d{2}-\d{4})\)", r.get("jornada", ""))
        rounds.append({"number": n, "date": _date(m.group(1)) if m else None, "matches": matches})

    played_rounds = [r["number"] for r in rounds if any(x["status"] == "played" for x in r["matches"])]
    last_played = max(played_rounds) if played_rounds else None
    current = current_round(rounds, today)
    return {
        "competition": raw.get("competicion"),
        "group": raw.get("grupo"),
        "season": raw.get("temporada"),
        "rounds": rounds,
        "lastPlayedRound": last_played,
        "currentRound": current,
    }


# --- Clasificación y goleadores -------------------------------------------

def normalize_standings(raw: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for t in raw.get("clasificacion", []):
        gf, gc = _int(t.get("goles_a_favor")) or 0, _int(t.get("goles_en_contra")) or 0
        rows.append(
            {
                "pos": _int(t.get("posicion")),
                "team": team(t["codequipo"], t["nombre"], (t.get("url_img") or "").split("?")[0]),
                "played": _int(t.get("jugados")) or 0,
                "won": _int(t.get("ganados")) or 0,
                "drawn": _int(t.get("empatados")) or 0,
                "lost": _int(t.get("perdidos")) or 0,
                "gf": gf,
                "ga": gc,
                "gd": gf - gc,
                "points": _int(t.get("puntos")) or 0,
                "penaltyPoints": _int(t.get("puntos_sancion")) or 0,
                "zone": (t.get("color") or "").strip() or None,
                "form": [x.get("tipo") for x in t.get("racha_partidos", [])],
            }
        )
    return {
        "round": _int(raw.get("jornada")),
        "roundDate": _date(raw.get("fecha_jornada")),
        "zones": [
            {"color": p.get("color"), "label": p.get("nombre") or p.get("descripcion")}
            for p in (raw.get("promociones") or [])
            if isinstance(p, dict) and p.get("color")
        ],
        "rows": rows,
    }


def normalize_scorers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for g in raw.get("goles", []):
        out.append(
            {
                "playerId": g.get("codigo_jugador"),
                "name": g.get("jugador"),
                "team": team(g.get("codigo_equipo", ""), g.get("nombre_equipo", ""), g.get("escudo_equipo")),
                "played": _int(g.get("partidos_jugados")) or 0,
                "goals": _int(g.get("goles")) or 0,
                "penalties": _int(g.get("goles_penalti")) or 0,
                "perGame": float(g.get("goles_por_partidos") or 0),
                "me": g.get("codigo_jugador") == settings.mi_jugador,
            }
        )
    out.sort(key=lambda s: (-s["goals"], s["played"], s["name"] or ""))
    return out


# --- Acta ----------------------------------------------------------------

def _card_kind(c: dict[str, Any]) -> str:
    # Observado: 100 = amarilla. Doble amarilla viene marcada aparte; el resto lo tratamos como roja.
    if str(c.get("segunda_amarilla")) == "1":
        return "second_yellow"
    return "yellow" if str(c.get("codigo_tipo_amonestacion")) == "100" else "red"


def _players(lst: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ps = [
        {
            "id": p.get("codjugador"),
            "name": p.get("nombre_jugador"),
            "number": _int(p.get("dorsal")),
            "starter": str(p.get("titular")) == "1",
            "goalkeeper": str(p.get("portero")) == "1",
            "captain": str(p.get("capitan")) == "1",
            "me": p.get("codjugador") == settings.mi_jugador,
        }
        for p in lst or []
    ]
    ps.sort(key=lambda p: (not p["starter"], not p["goalkeeper"], p["number"] or 999))
    return ps


def normalize_acta(raw: dict[str, Any]) -> dict[str, Any]:
    gh, ga = _int(raw.get("goles_local")), _int(raw.get("goles_visitante"))
    events: list[dict[str, Any]] = []
    for side, key in (("home", "goles_equipo_local"), ("away", "goles_equipo_visitante")):
        for g in raw.get(key) or []:
            # tipo_gol 102 = autogol: aparece en la lista del equipo del jugador,
            # pero suma para el rival (comprobado con el marcador del acta).
            own = str(g.get("tipo_gol")) == "102"
            events.append(
                {
                    "type": "goal",
                    "side": ("away" if side == "home" else "home") if own else side,
                    "minute": _int(g.get("minuto")),
                    "player": g.get("nombre_jugador"),
                    "playerId": g.get("codjugador"),
                    "ownGoal": own,
                }
            )
    for side, key in (("home", "tarjetas_equipo_local"), ("away", "tarjetas_equipo_visitante")):
        for c in raw.get(key) or []:
            events.append(
                {
                    "type": _card_kind(c),
                    "side": side,
                    "minute": _int(c.get("minuto")),
                    "player": c.get("nombre_jugador"),
                    "playerId": c.get("codjugador"),
                }
            )
    events.sort(key=lambda e: (e["minute"] is None, e["minute"] or 0, e["type"] != "goal"))

    played = gh is not None and ga is not None and (raw.get("acta_cerrada") == "1" or raw.get("partido_en_juego") == "1")
    return {
        "id": raw.get("codacta"),
        "competition": raw.get("nombre_competicion"),
        "group": raw.get("nombre_grupo"),
        "jornada": _int(raw.get("jornada")),
        "date": _date(raw.get("fecha")),
        "time": (raw.get("hora") or "").strip() or None,
        "venue": (raw.get("campo") or "").strip() or None,
        "closed": raw.get("acta_cerrada") == "1",
        "live": raw.get("partido_en_juego") == "1",
        "suspended": raw.get("suspendido") == "1",
        "home": team(raw.get("codigo_equipo_local", ""), raw.get("equipo_local", ""), raw.get("escudo_local", "").split("?")[0]),
        "away": team(raw.get("codigo_equipo_visitante", ""), raw.get("equipo_visitante", ""), raw.get("escudo_visitante", "").split("?")[0]),
        "score": {"home": gh, "away": ga} if played else None,
        "penalties": (
            {"home": _int(raw.get("penaltis_casa")), "away": _int(raw.get("penaltis_fuera"))}
            if raw.get("hay_penaltis") == "1"
            else None
        ),
        "events": events,
        "lineups": {
            "home": {
                "players": _players(raw.get("jugadores_equipo_local")),
                "coach": (raw.get("entrenador_local") or "").strip() or None,
                "delegate": (raw.get("delegadolocal") or "").strip() or None,
            },
            "away": {
                "players": _players(raw.get("jugadores_equipo_visitante")),
                "coach": (raw.get("entrenador_visitante") or "").strip() or None,
                "delegate": (raw.get("delegado_visitante") or "").strip() or None,
            },
        },
        "referees": [
            {"role": (r.get("tipo_arbitro") or "").title(), "name": r.get("nombre_arbitro")}
            for r in raw.get("arbitros_partido") or []
        ],
    }


# --- Servicio ------------------------------------------------------------

class Service:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def calendar(self) -> dict[str, Any]:
        raw = await cache.get_or_fetch("calendar", self.client.calendar, settings.ttl_calendario)
        return normalize_calendar(raw)

    async def standings(self, round_: int | None = None) -> dict[str, Any]:
        if round_ is None:
            cal = await self.calendar()
            round_ = cal["lastPlayedRound"] or 1
        r = str(round_)
        raw = await cache.get_or_fetch(
            f"standings:{r}", lambda: self.client.standings(r), settings.ttl_clasificacion
        )
        return normalize_standings(raw)

    async def scorers(self) -> list[dict[str, Any]]:
        raw = await cache.get_or_fetch("scorers", self.client.scorers, settings.ttl_goleadores)
        return normalize_scorers(raw)

    async def match(self, codacta: str) -> dict[str, Any]:
        raw = await cache.get_or_fetch(
            f"acta:{codacta}",
            lambda: self.client.acta(codacta),
            lambda v: settings.ttl_acta_cerrada if v.get("acta_cerrada") == "1" else settings.ttl_acta_abierta,
        )
        return normalize_acta(raw)

    async def team(self, team_id: str) -> dict[str, Any]:
        cal = await self.calendar()
        matches = [
            m for r in cal["rounds"] for m in r["matches"] if team_id in (m["home"]["id"], m["away"]["id"])
        ]
        if not matches:
            raise KeyError(team_id)
        info = matches[0]["home"] if matches[0]["home"]["id"] == team_id else matches[0]["away"]

        for m in matches:
            m["isHome"] = m["home"]["id"] == team_id
            m["result"] = result_for(m, team_id)

        played = [m for m in matches if m["status"] == "played"]
        upcoming = [m for m in matches if m["status"] == "scheduled"]
        standings = await self.standings()
        row = next((r for r in standings["rows"] if r["team"]["id"] == team_id), None)
        return {
            "team": info,
            "standing": row,
            "standingsRound": standings["round"],
            "totalTeams": len(standings["rows"]),
            "last": played[-1] if played else None,
            "next": upcoming[0] if upcoming else None,
            "form": [m["result"] for m in played[-5:]],
            "matches": matches,
        }

    async def player(self, player_id: str, team_id: str) -> dict[str, Any]:
        """Estadísticas personales sacadas de las actas de los partidos ya jugados."""
        cal = await self.calendar()
        played = [
            m
            for r in cal["rounds"]
            for m in r["matches"]
            if m["status"] == "played" and team_id in (m["home"]["id"], m["away"]["id"])
        ]
        sem = asyncio.Semaphore(4)  # no saturar a la RFFM

        async def load(mid: str) -> dict[str, Any] | None:
            async with sem:
                try:
                    return await self.match(mid)
                except Exception:
                    return None

        actas = await asyncio.gather(*(load(m["id"]) for m in played))
        name, games = None, []
        totals = {"called": 0, "starts": 0, "goals": 0, "yellow": 0, "red": 0, "conceded": 0,
                  "gkGames": 0, "cleanSheets": 0, "wins": 0, "draws": 0, "losses": 0}
        for m, a in zip(played, actas):
            if not a:
                continue
            side = "home" if a["home"]["id"] == team_id else "away"
            other = "away" if side == "home" else "home"
            me = next((p for p in a["lineups"][side]["players"] if p["id"] == player_id), None)
            if not me:
                continue
            name = name or me["name"]
            goals = sum(1 for e in a["events"] if e["type"] == "goal" and e["playerId"] == player_id and not e["ownGoal"])
            cards = [e["type"] for e in a["events"] if e["playerId"] == player_id and e["type"] != "goal"]
            conceded = (a["score"] or {}).get(other) if a["score"] else None
            res = result_for(m, team_id)
            totals["called"] += 1
            totals["starts"] += me["starter"]
            totals["goals"] += goals
            totals["yellow"] += sum(c in ("yellow", "second_yellow") for c in cards)
            totals["red"] += sum(c in ("red", "second_yellow") for c in cards)
            totals[{"G": "wins", "E": "draws", "P": "losses"}[res]] += 1
            # El acta no trae minutos jugados: los goles encajados solo se cuentan
            # en los partidos que empezaste de titular como portero.
            if me["goalkeeper"] and me["starter"]:
                totals["gkGames"] += 1
                totals["conceded"] += conceded or 0
                totals["cleanSheets"] += conceded == 0
            games.append(
                {
                    "match": m,
                    "number": me["number"],
                    "starter": me["starter"],
                    "goalkeeper": me["goalkeeper"],
                    "captain": me["captain"],
                    "goals": goals,
                    "cards": cards,
                    "conceded": conceded if (me["goalkeeper"] and me["starter"]) else None,
                    "result": res,
                }
            )
        return {"playerId": player_id, "name": name, "totals": totals, "games": games[::-1]}


def result_for(m: dict[str, Any], team_id: str) -> str | None:
    if m["status"] != "played":
        return None
    mine, theirs = (
        (m["score"]["home"], m["score"]["away"]) if m["home"]["id"] == team_id else (m["score"]["away"], m["score"]["home"])
    )
    return "G" if mine > theirs else "E" if mine == theirs else "P"
