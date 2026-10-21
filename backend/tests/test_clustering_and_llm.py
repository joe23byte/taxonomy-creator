import httpx
import numpy as np
import pytest

from app import clustering, extraction
from app.ollama_client import OllamaClient, StructuredOutputError
from fake_ollama import FakeOllama


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _blob(center, n, noise, rng):
    return _unit(center + rng.normal(scale=noise, size=(n, len(center))))


def test_hdbscan_groups_and_keeps_outliers():
    rng = np.random.default_rng(0)
    a, b = np.zeros(32), np.zeros(32)
    a[0], b[1] = 1, 1
    out = np.zeros(32)
    out[5] = 1
    X = np.vstack([_blob(a, 6, 0.05, rng), _blob(b, 5, 0.05, rng), _unit(out)[None, :]])
    res = clustering.cluster_candidates(X, 0.75)
    sizes = sorted(len(c.members) for c in res.clusters)
    assert sizes == [5, 6]
    assert res.outliers == [11]
    assert res.method.startswith("hdbscan")
    assert all(c.cohesion >= 0.75 for c in res.clusters)


def test_small_set_fallback_and_singletons():
    rng = np.random.default_rng(1)
    a = np.zeros(16)
    a[0] = 1
    c = np.zeros(16)
    c[3] = 1
    X = np.vstack([_blob(a, 2, 0.02, rng), _unit(c)[None, :]])
    res = clustering.cluster_candidates(X, 0.8)
    assert res.method == "agglomerative_small_set"
    assert [sorted(cl.members) for cl in res.clusters] == [[0, 1]]
    assert res.outliers == [2]
    assert clustering.cluster_candidates(X[:1], 0.8).outliers == [0]


def test_split_detection():
    rng = np.random.default_rng(2)
    a, b = np.zeros(16), np.zeros(16)
    a[0], b[1] = 1, 1
    X = np.vstack([_blob(a, 4, 0.05, rng), _blob(b, 4, 0.05, rng)])
    groups = clustering.find_subclusters(X, 0.75, separation=0.8)
    assert groups and sorted(len(g) for g in groups) == [4, 4]
    assert clustering.find_subclusters(_blob(a, 8, 0.05, rng), 0.75, 0.8) is None


def test_structured_output_retries_after_malformed_json():
    fake = FakeOllama(malformed_first=1)
    client = OllamaClient("http://x", transport=fake.transport())
    out = extraction.extract_intents(client, "qwen3:8b",
                                     [{"speaker": "customer", "text": "I was charged twice this month"}],
                                     [{"id": "L2-BIL-DSP", "label": "Billing Disputes", "description": "", "l1_label": "Billing"}])
    assert fake.calls["/api/chat"] == 2
    assert out.intents[0]["category_id"] == "L2-BIL-DSP"
    assert out.intents[0]["evidence_verified"] == 2
    assert fake.payloads[0]["think"] is False
    assert fake.payloads[0]["format"]["properties"]["intents"]["items"]["properties"]["category_id"]["enum"] == \
        ["L2-BIL-DSP", "UNMATCHED"]


def test_structured_output_gives_up_safely():
    fake = FakeOllama(malformed_first=10)
    client = OllamaClient("http://x", transport=fake.transport())
    with pytest.raises(StructuredOutputError) as e:
        extraction.extract_intents(client, "qwen3:8b", [{"speaker": "customer", "text": "secret words"}],
                                   [{"id": "L2-X", "label": "X", "description": "", "l1_label": "Y"}])
    assert "secret" not in str(e.value)


def test_gpt_oss_uses_reasoning_level():
    fake = FakeOllama()
    client = OllamaClient("http://x", transport=fake.transport())
    client.chat("gpt-oss:20b", [{"role": "system", "content": "health check"}, {"role": "user", "content": "x"}])
    assert fake.payloads[-1]["think"] == "low"


def test_unmatched_category_and_evidence_verification():
    turns = [{"speaker": "customer", "text": "Can you tell me a joke?"}]
    assert extraction.verify_evidence("tell me a joke", turns) == 2
    assert extraction.verify_evidence("completely invented quote", turns) == 0
    fake = FakeOllama()
    client = OllamaClient("http://x", transport=fake.transport())
    out = extraction.extract_intents(client, "qwen3:8b", turns,
                                     [{"id": "L2-X", "label": "X", "description": "", "l1_label": "Y"}])
    assert out.intents[0]["category_id"] is None


def test_connection_error_is_safe():
    def boom(request):
        raise httpx.ConnectError("refused")
    client = OllamaClient("http://10.0.0.9:11434", transport=httpx.MockTransport(boom))
    from app.ollama_client import OllamaError
    with pytest.raises(OllamaError) as e:
        client.embed("m", ["private text"])
    assert "private" not in str(e.value)


def test_clean_label_trims_dangling_words():
    from app.taxonomy import clean_label
    assert clean_label("mobile data connection is slow or unavailable in rural areas") == "Mobile Data Connection Is Slow Or Unavailable"
    assert clean_label("Data Connection Is Slow Or", max_words=5) == "Data Connection Is Slow"
    assert clean_label("  SIM  swap request. ") == "SIM Swap Request"
    assert clean_label("termin für Facharzt suchen", lang="de") == "Termin für Facharzt suchen"
    assert clean_label("Krankengeld Nicht Ausgezahlt und", lang="de") == "Krankengeld nicht Ausgezahlt"
