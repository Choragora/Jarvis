from fastapi.testclient import TestClient

from jarvis.app import create_app


def client(tmp_path):
    app = create_app(tmp_path, "test-bootstrap")
    return app, TestClient(app, base_url="http://127.0.0.1:8765")


def login(c):
    assert c.post("/api/session", json={"token": "test-bootstrap"}).status_code == 200


def test_authentication_origin_host_and_static_isolation(tmp_path):
    app, c = client(tmp_path)
    with c:
        assert c.get("/api/state").status_code == 401
        assert c.post("/api/session", json={"token": "wrong"}).status_code == 401
        login(c)
        assert c.get("/api/state").status_code == 200
        assert c.post("/api/stop", headers={"Origin": "https://attacker.example"}).status_code == 403
        assert c.get("/api/state", headers={"Host": "attacker.example"}).status_code == 403
        assert c.get("/api/settings").status_code == 200
        assert c.get("/assets/../memory.sqlite3").status_code == 404
        assert c.get("/api/captures/not-a-capture.png").status_code == 400
        assert c.get("/").headers["Content-Security-Policy"]
        cookie = c.cookies.get("jarvis_session")
        assert cookie and cookie != "test-bootstrap"


def test_notes_search_edit_export_and_graph(tmp_path):
    app, c = client(tmp_path)
    with c:
        login(c)
        a = c.post("/api/notes", json={"title": "Portugal", "body": "Respostas em português."}).json()
        b = c.post("/api/notes", json={"title": "Preferência", "body": "Ver [[Portugal]]"}).json()
        assert c.get("/api/notes?q=portugues").json()[0]["id"] == a["id"]
        graph = c.get("/api/graph").json()
        assert graph["links"] == [{"source": b["id"], "target": a["id"]}]
        c.put("/api/notes/" + a["id"], json={"title": "Portugal", "body": "Texto corrigido"})
        assert not c.get("/api/notes?q=portugues").json()
        assert len(c.get("/api/export").json()["notes"]) == 2
        c.delete("/api/notes/" + b["id"])
        assert not c.get("/api/graph").json()["links"]


def test_stop_settings_and_no_windows_claim(tmp_path):
    app, c = client(tmp_path)
    with c:
        login(c)
        assert c.post("/api/stop").json()["stopped"]
        assert c.get("/api/state").json()["stopped"]
        assert not c.post("/api/resume").json()["stopped"]
        settings = c.get("/api/settings").json()
        settings["hands_free"] = True
        assert c.put("/api/settings", json=settings).status_code == 422
        settings["hands_free"] = False
        settings["speaker"] = 1
        assert c.put("/api/settings", json=settings).status_code == 422
        if __import__("sys").platform != "win32":
            assert not c.get("/api/desktop").json()["monitors"]
            assert c.get("/api/desktop").json()["error"]


def test_websocket_requires_same_origin_and_session(tmp_path):
    app, c = client(tmp_path)
    with c:
        login(c)
        with c.websocket_connect(
            "ws://127.0.0.1:8765/api/events",
            headers={"origin": "http://127.0.0.1:8765", "host": "127.0.0.1:8765"},
        ) as ws:
            c.post("/api/stop")
            event = ws.receive_json()
            assert event["type"] == "stopped"
