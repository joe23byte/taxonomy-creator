from fastapi.testclient import TestClient

from app import db, main


def test_projects_are_isolated(tmp_db, fake):
    with TestClient(main.app) as client:
        listing = client.get("/api/projects").json()
        assert len(listing["projects"]) == 1
        first = listing["active"]
        assert client.get("/api/summary").json()["project"]["id"] == first
        assert client.post("/api/import/sample").json()["imported"] == 100

        assert client.post("/api/projects", json={"name": "  "}).status_code == 400
        created = client.post("/api/projects", json={"name": "Customer A", "description": "Q3 export"}).json()
        assert created["name"] == "Customer A"
        assert client.get("/api/projects").json()["active"] == first

        assert client.post(f"/api/projects/{created['id']}/activate").status_code == 200
        s = client.get("/api/summary").json()
        assert s["project"]["name"] == "Customer A" and s["interactions"] == 0
        assert db.get_db_path() != tmp_db
        assert client.get("/api/taxonomy").json()["nodes"] == []
        assert s["l1_nodes"] == 0

        assert client.delete(f"/api/projects/{created['id']}").status_code == 400
        client.patch(f"/api/projects/{created['id']}", json={"name": "Customer B"})
        stats = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
        assert stats[created["id"]]["name"] == "Customer B"
        assert stats[first]["stats"]["interactions"] == 100

        client.post(f"/api/projects/{first}/activate")
        assert client.get("/api/summary").json()["interactions"] == 100
        assert client.delete(f"/api/projects/{created['id']}").json() == {"ok": True}
        assert len(client.get("/api/projects").json()["projects"]) == 1
