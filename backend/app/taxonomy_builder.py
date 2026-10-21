"""LLM prompts that turn intent clusters into L3/L4 taxonomy decisions.

Every function validates the model output against the current taxonomy. Invalid ids
or empty labels are rejected here, so malformed responses never reach the taxonomy.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from . import language
from .ollama_client import OllamaClient

NEW = "NEW"
NONE = "NONE"

TAXONOMY_RULES = """Taxonomy levels: L1 domain > L2 topic (fixed) > L3 sub-topic > L4 specific intent.
- An L4 category names ONE specific customer intent (2-5 words), e.g. a concrete problem or request. It must not just repeat the L2 name.
- An L3 category is a broader sub-topic inside the L2 that can hold several related L4 categories (1-4 words).
- Reuse an existing L3 whenever the intent fits it. Create a new L3 only for a genuinely different sub-topic.
- Avoid synonyms of existing categories. Semantically similar but different problems (e.g. a lost card vs. replacing a damaged card) stay separate L4 categories.
- Descriptions: one sentence describing which customer situations belong in the category."""


def describe_existing(l3_nodes: list[dict], l4_by_l3: dict[str, list[dict]]) -> str:
    if not l3_nodes:
        return "(no L3/L4 categories exist yet under this L2)"
    lines = []
    for l3 in l3_nodes:
        lines.append(f"- L3 {l3['id']}: {l3['label']} — {l3['description']}")
        for l4 in l4_by_l3.get(l3["id"], []):
            lines.append(f"    - L4 {l4['id']}: {l4['label']} — {l4['description']}")
    return "\n".join(lines)


# --- cluster naming ------------------------------------------------------------------

class ClusterDecision(BaseModel):
    existing_l4_id: str
    l4_label: str = Field(default="", max_length=80)
    l4_description: str = Field(default="", max_length=400)
    l3_choice: str
    new_l3_label: str = Field(default="", max_length=80)
    new_l3_description: str = Field(default="", max_length=400)
    rationale: str = Field(default="", max_length=600)


@dataclass
class Decision:
    kind: str  # "existing" | "new"
    existing_l4_id: str | None
    l4_label: str
    l4_description: str
    l3_existing_id: str | None
    l3_label: str
    l3_description: str
    rationale: str


def _decision_schema(l3_ids: list[str], l4_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "existing_l4_id": {"type": "string", "enum": l4_ids + [NONE]},
            "l4_label": {"type": "string"},
            "l4_description": {"type": "string"},
            "l3_choice": {"type": "string", "enum": l3_ids + [NEW]},
            "new_l3_label": {"type": "string"},
            "new_l3_description": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["existing_l4_id", "l4_label", "l4_description", "l3_choice", "new_l3_label",
                     "new_l3_description", "rationale"],
    }


def _to_decision(out: ClusterDecision, l3_ids: set[str], l4_ids: set[str], lang: str = "en") -> Decision | None:
    out.l4_label = language.tidy_label(out.l4_label.strip(), lang)
    out.new_l3_label = language.tidy_label(out.new_l3_label.strip(), lang)
    if out.existing_l4_id in l4_ids:
        return Decision("existing", out.existing_l4_id, "", "", None, "", "", out.rationale)
    if not out.l4_label.strip():
        return None
    if out.l3_choice in l3_ids:
        return Decision("new", None, out.l4_label, out.l4_description, out.l3_choice, "", "", out.rationale)
    if not out.new_l3_label.strip():
        return None
    return Decision("new", None, out.l4_label, out.l4_description, None, out.new_l3_label, out.new_l3_description,
                    out.rationale)


def name_cluster(client: OllamaClient, model: str, l2: dict, l3_nodes: list[dict], l4_by_l3: dict[str, list[dict]],
                 statements: list[str], evidence: list[str],
                 exclude_l4: dict[str, float] | None = None, lang: str = "en") -> Decision | None:
    """exclude_l4 maps L4 ids the group must not be assigned to → their semantic similarity."""
    exclude_l4 = exclude_l4 or {}
    l3_ids = [n["id"] for n in l3_nodes]
    l4_ids = [n["id"] for ns in l4_by_l3.values() for n in ns if n["id"] not in exclude_l4]
    labels = {n["id"]: n["label"] for ns in l4_by_l3.values() for n in ns}
    system = ("You design a customer intent taxonomy for a contact center.\n" + TAXONOMY_RULES +
              "\nIf the group expresses exactly the same specific intent as an existing L4, return its id in "
              "existing_l4_id. Otherwise set existing_l4_id to NONE and propose a new L4, choosing an existing L3 "
              "id in l3_choice or NEW with a new L3 label." + language.rule(lang))
    user = (f"L2 category: {l2['l1_label']} > {l2['label']} — {l2['description']}\n\n"
            f"Existing categories under this L2:\n{describe_existing(l3_nodes, l4_by_l3)}\n\n"
            f"A group of {len(statements)} semantically similar customer intents was found:\n"
            + "\n".join(f"- {s}" for s in statements[:15])
            + ("\n\nExample customer quotes:\n" + "\n".join(f"- \"{e}\"" for e in evidence[:4]) if evidence else "")
            + "".join(f"\n\nNote: this group is semantically distinct from L4 {i} “{labels.get(i, i)}” (similarity "
                      f"{s:.2f}) and must not be assigned to it. Use another existing L4 only if it is exactly the "
                      f"same intent; otherwise propose a new L4." for i, s in exclude_l4.items())
            + "\n\nDecide how this group fits into the taxonomy.")
    out = client.chat_structured(model, system, user, ClusterDecision, schema=_decision_schema(l3_ids, l4_ids))
    return _to_decision(out, set(l3_ids), set(l4_ids), lang)


# --- outlier placement ---------------------------------------------------------------------

class OutlierItem(ClusterDecision):
    index: int
    action: str


class OutlierOutput(BaseModel):
    decisions: list[OutlierItem]


def place_outliers(client: OllamaClient, model: str, l2: dict, l3_nodes: list[dict], l4_by_l3: dict[str, list[dict]],
                   candidates: list[str], lang: str = "en") -> dict[int, tuple[str, Decision | None]]:
    """Return index -> (action, decision) with action in existing | new | unclassified."""
    l3_ids = [n["id"] for n in l3_nodes]
    l4_ids = [n["id"] for ns in l4_by_l3.values() for n in ns]
    item_schema = _decision_schema(l3_ids, l4_ids)
    item_schema["properties"]["index"] = {"type": "integer"}
    item_schema["properties"]["action"] = {"type": "string", "enum": ["existing_l4", "new_l4", "unclassified"]}
    item_schema["required"] = ["index", "action"] + item_schema["required"]
    schema = {"type": "object", "properties": {"decisions": {"type": "array", "items": item_schema}},
              "required": ["decisions"]}
    system = ("You design a customer intent taxonomy for a contact center.\n" + TAXONOMY_RULES +
              "\nYou receive rare customer intents that did not form a group with others. For each one decide:\n"
              "- existing_l4: it is the same specific intent as an existing L4 (give existing_l4_id)\n"
              "- new_l4: it is a distinct, clearly described intent that deserves its own L4 (give labels; "
              "existing_l4_id NONE)\n- unclassified: too vague or not a real request.\n"
              "If several listed intents are the same, give them the identical new L4 label." + language.rule(lang))
    user = (f"L2 category: {l2['l1_label']} > {l2['label']} — {l2['description']}\n\n"
            f"Existing categories under this L2:\n{describe_existing(l3_nodes, l4_by_l3)}\n\n"
            "Intents:\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(candidates)) +
            "\n\nReturn one decision per intent index.")
    out = client.chat_structured(model, system, user, OutlierOutput, schema=schema)
    result: dict[int, tuple[str, Decision | None]] = {}
    for d in out.decisions:
        if not 0 <= d.index < len(candidates) or d.index in result:
            continue
        if d.action == "unclassified":
            result[d.index] = ("unclassified", None)
            continue
        dec = _to_decision(d, set(l3_ids), set(l4_ids), lang)
        if dec is None or (d.action == "existing_l4" and dec.kind != "existing"):
            result[d.index] = ("unclassified", None)
        else:
            result[d.index] = (dec.kind, dec)
    return result


# --- description refinement ---------------------------------------------------------------

class Refinement(BaseModel):
    description: str = Field(max_length=400)


def refine_description(client: OllamaClient, model: str, label: str, description: str, statements: list[str],
                       lang: str = "en") -> str | None:
    system = ("You maintain a customer intent taxonomy. Rewrite the category description so it accurately covers "
              "the supporting customer intents. One or two sentences, generic wording, no examples with names or "
              "numbers. Keep the meaning of the category label." + language.rule(lang))
    user = (f"Category: {label}\nCurrent description: {description}\n\nSupporting intents:\n"
            + "\n".join(f"- {s}" for s in statements[:20]))
    out = client.chat_structured(model, system, user, Refinement)
    text = out.description.strip()
    return text if len(text) >= 10 else None


# --- split naming --------------------------------------------------------------------------------

class SplitPart(BaseModel):
    group: int
    label: str = Field(max_length=80)
    description: str = Field(default="", max_length=400)


class SplitOutput(BaseModel):
    should_split: bool
    parts: list[SplitPart] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=600)


def propose_split_labels(client: OllamaClient, model: str, label: str, description: str,
                         groups: list[list[str]], lang: str = "en") -> SplitOutput | None:
    system = ("You maintain a customer intent taxonomy. A category may contain distinct specific intents that should "
              "be separate L4 categories. Decide whether the groups below are genuinely different customer intents. "
              "If yes, give each group a specific 2-5 word label and a one sentence description." + language.rule(lang))
    user = (f"Category: {label} — {description}\n\n" + "\n\n".join(
        f"Group {gi}:\n" + "\n".join(f"- {s}" for s in g[:10]) for gi, g in enumerate(groups)))
    out = client.chat_structured(model, system, user, SplitOutput)
    if not out.should_split:
        return None
    seen = {p.group for p in out.parts if 0 <= p.group < len(groups) and p.label.strip()}
    if len(seen) != len(groups):
        return None
    for part in out.parts:
        part.label = language.tidy_label(part.label.strip(), lang)
    return out
