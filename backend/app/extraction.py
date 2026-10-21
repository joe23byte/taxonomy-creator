"""LLM-based extraction of atomic customer intents from one transcript."""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from . import language
from .ollama_client import OllamaClient

UNMATCHED = "UNMATCHED"
MAX_TRANSCRIPT_CHARS = 12000
MAX_INTENTS = 5

SYSTEM_PROMPT = """You are an expert customer service analyst. The category list shows the industry and the domain.
You read a transcript between a customer and an agent and identify what the CUSTOMER actually wants or which problem they need solved.

Rules:
- Extract every distinct customer request or problem as a separate atomic intent. Most conversations contain one intent; some contain two or three.
- Ignore greetings, thanks, small talk, identity verification and anything that is not a customer need.
- Do not split one request into several intents, and do not list the same need twice.
- "intent": a short normalized description (4-12 words) in neutral, generic wording that states the specific need or problem. It must be more specific than the category name. No names, numbers, dates, amounts or places. Example: "SMS verification codes are not received".
- "category_id": the single best-fitting category ID from the list. Use UNMATCHED only if no category fits at all.
- "evidence": a short verbatim quote copied exactly from a CUSTOMER turn that shows the intent.
- "reasoning": one short sentence explaining why the category fits.
- "summary": one sentence summarizing why the customer contacted support.
- If the customer has no actual request, return an empty "intents" list and explain why in "no_intent_reason"."""


class ExtractedIntent(BaseModel):
    intent: str = Field(min_length=3, max_length=200)
    category_id: str
    evidence: str = Field(default="", max_length=600)
    reasoning: str = Field(default="", max_length=600)

    @field_validator("intent")
    @classmethod
    def _tidy(cls, v: str) -> str:
        return re.sub(r"\s+", " ", v).strip().rstrip(".")


class ExtractionOutput(BaseModel):
    summary: str = Field(default="", max_length=600)
    intents: list[ExtractedIntent] = Field(default_factory=list)
    no_intent_reason: str | None = None


def build_schema(category_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "intents": {
                "type": "array",
                "maxItems": MAX_INTENTS,
                "items": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "category_id": {"type": "string", "enum": category_ids + [UNMATCHED]},
                        "evidence": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["intent", "category_id", "evidence", "reasoning"],
                },
            },
            "no_intent_reason": {"type": ["string", "null"]},
        },
        "required": ["summary", "intents"],
    }


def format_transcript(turns: list[dict], max_chars: int = MAX_TRANSCRIPT_CHARS) -> str:
    lines = []
    for t in turns:
        speaker = {"customer": "Customer", "agent": "Agent"}.get(t.get("speaker"), "System")
        lines.append(f"{speaker}: {t.get('text', '').strip()}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[transcript truncated]"
    return text


def format_categories(categories: list[dict]) -> str:
    return "\n".join(f"- {c['id']} | {c['l1_label']} > {c['label']}: {c['description']}" for c in categories)


def _tokens(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def verify_evidence(evidence: str, turns: list[dict]) -> int:
    """2 = verbatim in a customer turn, 1 = approximately present, 0 = not found."""
    if not evidence.strip():
        return 0
    customer = " ".join(t["text"] for t in turns if t.get("speaker") == "customer")
    ev, cu = " ".join(_tokens(evidence)), " ".join(_tokens(customer))
    if ev and ev in cu:
        return 2
    ev_t = _tokens(evidence)
    cu_t = set(_tokens(customer))
    if ev_t and sum(1 for t in ev_t if t in cu_t) / len(ev_t) >= 0.8:
        return 1
    return 0


@dataclass
class ExtractionResult:
    summary: str
    intents: list[dict]
    no_intent_reason: str | None
    dropped: int


def extract_intents(client: OllamaClient, model: str, turns: list[dict], categories: list[dict],
                    lang: str = "en") -> ExtractionResult:
    valid = {c["id"] for c in categories}
    schema = build_schema(sorted(valid))
    user = (f"Categories:\n{format_categories(categories)}\n\nTranscript:\n{format_transcript(turns)}\n\n"
            f"Return the JSON analysis of the customer's intents.")
    system = SYSTEM_PROMPT + language.rule(lang) + (
        " The evidence quote stays verbatim in the transcript's language." if lang != "en" else "")
    out = client.chat_structured(model, system, user, ExtractionOutput, schema=schema)
    intents: list[dict] = []
    seen: set[str] = set()
    dropped = 0
    for it in out.intents[:MAX_INTENTS]:
        key = " ".join(_tokens(it.intent))
        if not key or key in seen:
            dropped += 1
            continue
        seen.add(key)
        cat = it.category_id if it.category_id in valid else None
        intents.append({
            "intent": it.intent[:200],
            "category_id": cat,
            "raw_category": it.category_id if cat is None else None,
            "evidence": it.evidence.strip()[:600],
            "evidence_verified": verify_evidence(it.evidence, turns),
            "reasoning": it.reasoning.strip()[:600],
        })
    return ExtractionResult(out.summary.strip()[:600], intents, (out.no_intent_reason or None), dropped)
