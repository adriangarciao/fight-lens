from tests.conftest import fighter_id


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_search_ranks_prefix_matches(client):
    res = client.get("/api/fighters/search", params={"q": "bell"}).json()
    assert [r["name"] for r in res] == ["Bravo Bell"]
    res = client.get("/api/fighters/search", params={"q": "bruno"}).json()
    assert len(res) == 2 and {r["latest_division"] for r in res} == {"Flyweight", "Middleweight"}


def test_search_requires_two_chars(client):
    assert client.get("/api/fighters/search", params={"q": "a"}).status_code == 422


def test_fighter_detail_and_404(client, loaded):
    fid = fighter_id(loaded, "Alpha Ace")
    body = client.get(f"/api/fighters/{fid}", params={"asOf": "2026-10-20"}).json()
    assert body["record"]["wins"] == 3 and len(body["all_fights"]) == 5
    assert client.get("/api/fighters/99999").status_code == 404


def test_matchup(client, loaded):
    a, b = fighter_id(loaded, "Alpha Ace"), fighter_id(loaded, "Bravo Bell")
    res = client.get("/api/matchups", params={"fighterA": a, "fighterB": b, "asOf": "2026-10-20"})
    assert res.status_code == 200
    body = res.json()
    assert len(body["head_to_head"]) == 2 and len(body["common_opponents"]) == 2
    assert client.get("/api/matchups", params={"fighterA": a, "fighterB": a}).status_code == 422
    hist = client.get("/api/matchups/history", params={"fighterA": a, "fighterB": b}).json()
    assert len(hist["meetings"]) == 2


def test_events(client):
    upcoming = client.get("/api/events/upcoming").json()
    assert [e["name"] for e in upcoming] == ["UFC 999"]
    assert upcoming[0]["status"] == "scheduled"
    card = client.get(f"/api/events/{upcoming[0]['id']}").json()
    bout = card["bouts"][0]
    assert bout["status"] == "scheduled" and bout["prediction"] is None
    # Records on a card are as of the event date.
    assert bout["record_1"]["wins"] == 3
    recent = client.get("/api/events/recent").json()
    assert recent[0]["name"] == "UFC F"
    assert client.get("/api/events/99999").status_code == 404
