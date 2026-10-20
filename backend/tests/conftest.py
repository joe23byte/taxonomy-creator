import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, db, importers, pipeline  # noqa: E402
from app.ollama_client import OllamaClient  # noqa: E402
from fake_ollama import FakeOllama  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db.set_db_path(tmp_path / "test.db")
    db.init_db()
    yield tmp_path / "test.db"
    db.set_db_path(config.DB_PATH)


@pytest.fixture()
def fake(monkeypatch):
    f = FakeOllama()
    monkeypatch.setattr(pipeline, "make_client",
                        lambda s: OllamaClient("http://fake-ollama:11434", timeout=5, transport=f.transport()))
    return f


@pytest.fixture()
def conn(tmp_db):
    c = db.connect()
    yield c
    c.close()


def load_sample(conn, limit: int | None = None) -> int:
    data = json.loads((config.SAMPLE_DIR / "sample_transcripts.json").read_text())
    if limit:
        data = data[:limit]
    res = importers.parse_upload([("sample.json", json.dumps(data).encode())])
    return importers.commit(conn, "test sample", "json", res.records)["imported"]
