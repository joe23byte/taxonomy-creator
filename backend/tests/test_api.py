import time

from fastapi.testclient import TestClient

from app import main


def test_api_end_to_end(tmp_db, fake):
    with TestClient(main.app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        s = client.get("/api/summary").json()
        assert s["interactions"] == 0 and s["run"] is None
        tax = client.get("/api/taxonomy").json()
        assert {n["level"] for n in tax["nodes"]} == {1, 2}
        assert len([n for n in tax["nodes"] if n["level"] == 2]) == 14

        assert client.post("/api/import/sample").json()["imported"] == 100
        assert client.post("/api/import/sample").json()["skipped_existing"] == 100

        # CSV preview + commit with mapping
        csv = "id,text_full\nN1,\"Customer: my roaming bill is wrong\nAgent: ok\"\n"
        prev = client.post("/api/import/preview", files={"files": ("n.csv", csv, "text/csv")}).json()
        assert prev["total"] == 1 and prev["mapping"]["conversation_id"] == "id"
        assert client.post("/api/import/commit", json={"token": prev["token"]}).json()["imported"] == 1

        template = client.get("/api/import/template.json").content
        prev = client.post("/api/import/preview", files={"files": ("t.json", template, "application/json")}).json()
        assert prev["total"] == 2 and not [i for i in prev["issues"] if i["level"] == "error"]

        client.put("/api/settings", json={"batch_size": 50})
        assert client.get("/api/settings").json()["batch_size"] == 50
        assert client.put("/api/settings", json={"batch_size": 0}).status_code == 400

        test = client.post("/api/settings/test", json={"ollama_url": "http://fake-ollama:11434"})
        assert test.status_code == 200  # real network call fails gracefully (no fake transport here)

        assert client.post("/api/analysis/start").status_code == 200
        assert client.post("/api/analysis/start").status_code == 409
        for _ in range(300):
            if not main.worker.is_running():
                break
            time.sleep(0.1)
        s = client.get("/api/summary").json()
        assert s["processed"] == 101 and s["l4_nodes"] > 0

        rows = client.get("/api/interactions").json()
        detail = client.get(f"/api/interactions/{rows[0]['id']}").json()
        assert detail["turns"] and "intents" in detail
        aid = next(i["assignment"]["id"] for r in rows for i in client.get(f"/api/interactions/{r['id']}").json()["intents"]
                   if i["assignment"] and i["assignment"]["l4_id"])
        assert client.post(f"/api/assignments/{aid}/review", json={"action": "confirm"}).json()["review_status"] == "confirmed"
        assert client.post(f"/api/assignments/{aid}/review", json={"action": "correct",
                                                                   "path": {"l2_id": "L2-BIL-DSP", "l1_id": "L1-NET"}}).status_code == 400
        r = client.patch(f"/api/interactions/{rows[1]['id']}/review", json={"flag": True, "notes": "check"}).json()
        assert r["review_status"] == "needs_review" and r["reviewer_notes"] == "check"

        node = next(n for n in client.get("/api/taxonomy").json()["nodes"] if n["level"] == 4)
        d = client.get(f"/api/taxonomy/nodes/{node['id']}").json()
        assert d["examples"] and d["history"]
        renamed = client.patch(f"/api/taxonomy/nodes/{node['id']}", json={"label": "Renamed Category"}).json()
        assert renamed["label"] == "Renamed Category"

        ev = client.get("/api/events?limit=5").json()
        assert len(ev) == 5 and ev[0]["id"] > ev[-1]["id"]
        assert client.get("/api/insights/curve").json()["points"]
        evaluation = client.get("/api/insights/evaluation").json()
        assert evaluation["available"] and evaluation["evaluated"] == 100

        x = client.get("/api/export/xlsx")
        assert x.status_code == 200 and x.content[:2] == b"PK"
        c = client.get("/api/export/csv?sheet=Interaction Assignments")
        assert c.status_code == 200 and b"Conversation ID" in c.content
        assert client.get("/api/export/csv").headers["content-type"] == "application/zip"
        j = client.get("/api/export/json").json()
        assert len(j["assignments"]) >= 101

        assert client.post("/api/analysis/reset").json()["ok"]
        assert client.get("/api/summary").json()["l4_nodes"] == 0
