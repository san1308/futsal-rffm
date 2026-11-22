import json
from datetime import date
from pathlib import Path

import pytest

from app.cache import cache
from app.rffm import DemoClient, extract_next_data
from app.service import Service, normalize_acta, normalize_calendar, short_name

FX = Path(__file__).parent / "fixtures"
MI_EQUIPO = "17146426"
YO = "2799670"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("C.D.E. CASCO ANTIGUO CARABANCHEL 'A'", "Casco Antiguo Carabanchel"),
        ("CLUB ARGANDA FUTSAL - ALBERO-MUDANZAS SEGOVIANA 'A'", "Arganda Futsal"),
        ("DON P'ALPIE ARANJUEZ F.S.- CAFETERIA LA TACITA", "Don P'Alpie Aranjuez"),
        ("CDE C.F.S. EUROSIRIS - BINGO LAS VEGAS 'A'", "Eurosiris"),
        ("C.D.E. CIUDAD VILLA DE VALLECAS F.S.", "Ciudad Villa de Vallecas"),
        ("C.D.E. ANDRES SEGOVIA-MOSTOLES 'A'", "Andres Segovia-Mostoles"),
        ("A.D. OBISPO PERELLO A", "Obispo Perello"),
        ("F.S. DIAGONAL 'A'", "Diagonal"),
    ],
)
def test_short_name(raw, expected):
    assert short_name(raw) == expected


def test_calendar_rounds_and_status():
    cal = normalize_calendar(load("calendar.json"), today=date(2026, 10, 6))
    assert [r["number"] for r in cal["rounds"]] == [1, 2, 3, 4, 5, 6]
    assert cal["lastPlayedRound"] == 3
    assert cal["currentRound"] == 4
    j3 = cal["rounds"][2]["matches"]
    casco = next(m for m in j3 if m["id"] == "5575900")
    assert casco["score"] == {"home": 2, "away": 3}
    assert casco["home"]["mine"] is True
    assert casco["date"] == "2026-10-03" and casco["time"] == "17:10"
    pend = next(m for m in cal["rounds"][3]["matches"] if m["id"] == "5575903")
    assert pend["status"] == "scheduled" and pend["time"] is None and pend["score"] is None


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 1), 3),   # entre semana antes de la J3
        (date(2026, 10, 4), 3),   # domingo de la J3
        (date(2026, 10, 5), 4),   # lunes siguiente
        (date(2026, 10, 11), 4),  # domingo de la J4
        # La J4 tiene partidos sin jugar: aun así, la semana siguiente toca la J5
        (date(2026, 10, 14), 5),
        (date(2026, 10, 20), 6),
        (date(2026, 11, 9), 6),   # pasado el calendario: la última
    ],
)
def test_current_round_follows_the_calendar(today, expected):
    cal = normalize_calendar(load("calendar.json"), today=today)
    assert cal["currentRound"] == expected


def test_own_goal_counts_for_rival():
    a = normalize_acta(load("acta_5575892.json"))  # Villaverde 6-2 Casco
    goals = [e for e in a["events"] if e["type"] == "goal"]
    assert sum(e["side"] == "home" for e in goals) == 6
    assert sum(e["side"] == "away" for e in goals) == 2
    own = next(e for e in goals if e["ownGoal"])
    assert own["player"] == "ELIAS NICOLAS, JESUS" and own["side"] == "home"


def test_acta_lineups_order_and_me():
    a = normalize_acta(load("acta_5575900.json"))
    home = a["lineups"]["home"]["players"]
    assert home[0]["me"] and home[0]["goalkeeper"] and home[0]["starter"]
    assert all(p["starter"] for p in home[:5]) and not home[5]["starter"]
    assert len(a["referees"]) == 3
    assert a["events"][0]["minute"] == 3


@pytest.mark.asyncio
async def test_team_view():
    s = Service(DemoClient())
    t = await s.team(MI_EQUIPO)
    assert t["standing"]["pos"] == 10 and t["standing"]["points"] == 3
    assert t["form"] == ["G", "P", "P"]
    assert t["next"]["id"] == "5575909" and t["next"]["isHome"] is False
    assert t["last"]["id"] == "5575900"


@pytest.mark.asyncio
async def test_score_from_acta_when_calendar_is_late():
    """El calendario aún no tiene el resultado, pero el acta sí: se usa el del acta."""

    class LateCalendar(DemoClient):
        async def calendar(self):
            cal = load("calendar.json")
            for r in cal["rounds"]:
                for m in r["equipos"]:
                    if m["codacta"] == "5575900":
                        m["goles_casa"] = m["goles_visitante"] = ""
            return cal

    s = Service(LateCalendar())
    cal = await s.calendar(today=date(2026, 10, 6))
    m = next(m for r in cal["rounds"] for m in r["matches"] if m["id"] == "5575900")
    assert m["status"] == "played" and m["score"] == {"home": 2, "away": 3}
    assert cal["lastPlayedRound"] == 3
    # Partidos futuros o sin acta disponible siguen pendientes
    j4 = next(r for r in cal["rounds"] if r["number"] == 4)
    assert all(x["status"] == "scheduled" for x in j4["matches"])


@pytest.mark.asyncio
async def test_player_stats():
    s = Service(DemoClient())
    me = await s.player(YO, MI_EQUIPO)
    tot = me["totals"]
    assert me["name"] == "SANCHEZ NEGRO, ADRIAN"
    assert tot["called"] == 3 and tot["starts"] == 2
    assert tot["gkGames"] == 2 and tot["conceded"] == 2 + 3
    assert tot["wins"] == 1 and tot["losses"] == 2
    assert me["games"][0]["match"]["id"] == "5575900"  # más reciente primero


@pytest.mark.asyncio
async def test_live_client_with_mocked_rffm():
    import httpx

    from app.rffm import RFFMClient

    cal = load("calendar.json")
    acta = load("acta_5575900.json")

    def page(props):
        data = json.dumps({"props": {"pageProps": props}, "page": "/x", "buildId": "abc"})
        return f'<html><body><script id="__NEXT_DATA__" type="application/json">{data}</script></body></html>'

    def handler(req: httpx.Request):
        p = req.url.path
        if p == "/competicion/calendario":
            assert req.url.params["grupo"] == "26771028"
            return httpx.Response(200, text=page({"calendar": cal, "currentRound": "3"}))
        if p == "/acta-partido/5575900":
            return httpx.Response(200, text=page({"game": acta}))
        if p == "/api/standings":
            return httpx.Response(200, json=load("standings.json"))
        if p == "/api/scorers":
            return httpx.Response(200, json=load("scorers.json"))
        return httpx.Response(404)

    client = RFFMClient(httpx.AsyncClient(base_url="https://www.rffm.es", transport=httpx.MockTransport(handler)))
    s = Service(client)
    assert (await s.calendar())["lastPlayedRound"] == 3
    assert (await s.standings())["rows"][0]["points"] == 9
    assert (await s.match("5575900"))["score"] == {"home": 2, "away": 3}
    assert (await s.scorers())[0]["goals"] == 7


def test_extract_next_data():
    html = '<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"x":1}}}</script></html>'
    assert extract_next_data(html)["props"]["pageProps"]["x"] == 1


async def test_standings_salta_jornadas_sin_datos():
    """La RFFM responde `null` en algunas jornadas: se usa la más reciente con datos."""
    import httpx

    from app.rffm import RFFMClient, RFFMError

    cal = load("calendar.json")
    pedidas = []
    sin_datos: set[str] = set()

    def page(props):
        data = json.dumps({"props": {"pageProps": props}, "page": "/x", "buildId": "abc"})
        return f'<html><body><script id="__NEXT_DATA__" type="application/json">{data}</script></body></html>'

    def handler(req: httpx.Request):
        p = req.url.path
        if p == "/competicion/calendario":
            return httpx.Response(200, text=page({"calendar": cal, "currentRound": "4"}))
        if p == "/api/standings":
            rnd = req.url.params["round"]
            pedidas.append(rnd)
            if rnd in sin_datos:
                return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})
            return httpx.Response(200, json=load("standings.json"))
        return httpx.Response(404)

    client = RFFMClient(httpx.AsyncClient(base_url="https://www.rffm.es", transport=httpx.MockTransport(handler)))
    s = Service(client)
    c = await s.calendar()
    actual, ultima = c["currentRound"], c["lastPlayedRound"]
    sin_datos.update({str(actual), str(ultima)})
    assert (await s.standings())["rows"][0]["points"] == 9
    assert pedidas == [str(actual), str(ultima), str(ultima - 1)]
    with pytest.raises(RFFMError):
        await s.standings(ultima)


@pytest.mark.asyncio
async def test_player_stats_with_edits(tmp_path):
    from app.store import StatsStore

    store = StatsStore(tmp_path / "stats.json")
    s = Service(DemoClient(), store)
    base = await s.player(YO, MI_EQUIPO)
    g = next(x for x in base["games"] if x["conceded"] is not None)
    store.set(YO, g["match"]["id"], {**g["acta"], "conceded": g["acta"]["conceded"] + 1, "goals": 2, "assists": 1})

    me = await s.player(YO, MI_EQUIPO)
    tot = me["totals"]
    assert tot["conceded"] == base["totals"]["conceded"] + 1
    assert tot["goals"] == base["totals"]["goals"] + 2 - g["acta"]["goals"]
    assert tot["assists"] == 1
    edited = next(x for x in me["games"] if x["match"]["id"] == g["match"]["id"])
    assert set(edited["edited"]) == {"conceded", "goals", "assists"}
    assert edited["acta"] == g["acta"]  # lo del acta se conserva para poder volver

    # Desconvocarme de un partido lo quita de los totales y lo pasa a "otros"
    store.set(YO, g["match"]["id"], {"called": False})
    me = await s.player(YO, MI_EQUIPO)
    assert me["totals"]["called"] == base["totals"]["called"] - 1
    assert any(x["match"]["id"] == g["match"]["id"] for x in me["others"])

    store.delete(YO, g["match"]["id"])
    assert (await s.player(YO, MI_EQUIPO))["totals"] == base["totals"]


def test_store_validation(tmp_path):
    from app.store import StatsStore

    store = StatsStore(tmp_path / "stats.json")
    for bad in ({"goals": -1}, {"goals": "3"}, {"called": 1}, {"hack": True}, {"goals": True}):
        with pytest.raises(ValueError):
            store.set(YO, "1", bad)
    assert store.set(YO, "1", {"conceded": None, "goals": 3}) == {"conceded": None, "goals": 3}
    assert StatsStore(tmp_path / "stats.json").for_player(YO) == {"1": {"conceded": None, "goals": 3}}


def test_edit_api(tmp_path, monkeypatch):
    import dataclasses

    from fastapi.testclient import TestClient

    import app.main as main
    import app.service as service

    test_settings = dataclasses.replace(main.settings, demo=True, edit_key="secreto", stats_file=str(tmp_path / "s.json"))
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(service, "settings", test_settings)
    with TestClient(main.app) as c:
        assert c.put("/api/me/games/5575900", json={"goals": 1}).status_code == 401
        assert c.put("/api/me/games/5575900", json={"goals": 1}, headers={"X-Edit-Key": "mal"}).status_code == 401
        h = {"X-Edit-Key": "secreto"}
        assert c.put("/api/me/games/5575900", json={"goals": -2}, headers=h).status_code == 422
        assert c.put("/api/me/games/5575900", json={"goals": 4, "assists": 2}, headers=h).status_code == 200
        me = c.get("/api/me").json()
        g = next(x for x in me["games"] if x["match"]["id"] == "5575900")
        assert g["goals"] == 4 and g["assists"] == 2 and me["editable"]
        assert c.delete("/api/me/games/5575900", headers=h).status_code == 200
