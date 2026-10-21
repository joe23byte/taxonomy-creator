"""Deterministic fake Ollama server (httpx MockTransport) for automated tests only."""
from __future__ import annotations

import hashlib
import json
import re

import httpx
import numpy as np

KEYWORDS = [
    (r"twice|double|duplicate|two debits", "Charged twice for the same monthly bill", "L2-BIL-DSP"),
    (r"top-up|topped up|recharg|voucher|loaded credit|top up", "Prepaid top-up credit not received", "L2-PRD-TOP"),
    (r"slow|buffering|crawling|unusable", "Mobile data speed is very slow", "L2-NET-DAT"),
    (r"password", "Needs to reset account password", "L2-ACC-ACS"),
    (r"roaming", "Unexpected roaming charges after travelling", "L2-BIL-DSP"),
    (r"invoice|line item|bill is higher|first bill|go through my bill", "Wants explanation of invoice items", "L2-BIL-INV"),
    (r"declined|payment keeps failing|direct debit failed|payment unsuccessful|didn't go through", "Bill payment fails or is declined", "L2-BIL-PAY"),
    (r"no signal|no service|network down|network was down|network outage|network has been completely dead|outage", "No network signal in local area", "L2-NET-COV"),
]


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


def fake_vector(text: str, dim: int = 64) -> list[float]:
    """Bag-of-words random projection: shared words → similar vectors."""
    text = text.split("Query: ", 1)[-1]
    v = np.zeros(dim)
    for tok in _tokens(text):
        if len(tok) < 3:
            continue
        seed = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)
        v += np.random.default_rng(seed).normal(size=dim)
    n = np.linalg.norm(v) or 1.0
    return (v / n).tolist()


class FakeOllama:
    def __init__(self, malformed_first: int = 0, fail_chat: bool = False):
        self.calls: dict[str, int] = {}
        self.malformed_remaining = malformed_first
        self.fail_chat = fail_chat
        self.payloads: list[dict] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls[path] = self.calls.get(path, 0) + 1
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}, {"name": "qwen3-embedding:0.6b"}]})
        body = json.loads(request.content or b"{}")
        self.payloads.append(body)
        if path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [fake_vector(t) for t in body["input"]]})
        if path == "/api/chat":
            if self.fail_chat:
                return httpx.Response(500, json={"error": "model crashed"})
            if self.malformed_remaining > 0:
                self.malformed_remaining -= 1
                return httpx.Response(200, json={"message": {"content": "{not json"}})
            content = self.answer(body["messages"][0]["content"], body["messages"][1]["content"], body.get("format"))
            return httpx.Response(200, json={"message": {"content": json.dumps(content)}})
        return httpx.Response(404, json={"error": "not found"})

    def answer(self, system: str, user: str, schema: dict | None) -> dict:
        if "health check" in system:
            return {"status": "ok"}
        if "contact center analyst" in system:
            return {"rationale": "Frequent intent in the analysed interactions; worth examining for clearer information."}
        if "expert customer service analyst" in system:
            transcript = user.split("Transcript:", 1)[1]
            customer = [l[len("Customer: "):] for l in transcript.splitlines() if l.startswith("Customer: ")]
            intents, used = [], set()
            for line in customer:
                for pattern, text, cat in KEYWORDS:
                    if text not in used and re.search(pattern, line.lower()):
                        used.add(text)
                        intents.append({"intent": text, "category_id": cat, "evidence": line[:80],
                                        "reasoning": "Keyword match in fake model"})
            if not intents and customer:
                intents.append({"intent": "General question about the mobile service", "category_id": "UNMATCHED",
                                "evidence": customer[0][:60], "reasoning": "No category"})
            return {"summary": "Customer contacted support.", "intents": intents, "no_intent_reason": None}
        if "rare customer intents" in system:
            items = re.findall(r"^(\d+)\. (.+)$", user, flags=re.M)
            return {"decisions": [{"index": int(i), "action": "new_l4", "existing_l4_id": "NONE",
                                   "l4_label": " ".join(t.split()[:3]), "l4_description": t, "l3_choice": "NEW",
                                   "new_l3_label": "Other Requests", "new_l3_description": "Rare requests",
                                   "rationale": "rare"} for i, t in items]}
        if "design a customer intent taxonomy" in system:
            statements = re.findall(r"^- (?!L[34] )(.+)$", user.split("was found:", 1)[1], flags=re.M)
            first = statements[0] if statements else "Unknown intent"
            l3_enum = schema["properties"]["l3_choice"]["enum"]
            l3 = l3_enum[0] if len(l3_enum) > 1 else "NEW"
            return {"existing_l4_id": "NONE", "l4_label": " ".join(first.split()[:4]),
                    "l4_description": f"Customers report: {first}", "l3_choice": l3,
                    "new_l3_label": "Core Issues", "new_l3_description": "Main issues in this topic",
                    "rationale": "Fake naming"}
        if "Rewrite the category description" in system:
            return {"description": "Refined description covering all supporting intents."}
        if "should be separate" in system or "distinct specific intents" in system:
            return {"should_split": False, "parts": [], "rationale": "no"}
        return {}
