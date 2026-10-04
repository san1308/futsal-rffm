import json
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
    cal = normalize_calendar(load("calendar.json"))
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
