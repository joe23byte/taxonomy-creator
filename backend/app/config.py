"""Application configuration.

Environment variables provide defaults; values saved through the Settings UI are
stored in SQLite and take precedence at runtime.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
load_dotenv(REPO_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
SAMPLE_DIR = DATA_DIR / "sample"
TAXONOMY_SEED_PATH = Path(os.getenv("INTENT_STUDIO_TAXONOMY_SEED", DATA_DIR / "taxonomy_seed.json"))
DB_PATH = Path(os.getenv("INTENT_STUDIO_DB_PATH", BACKEND_DIR / "var" / "intent_studio.db"))
HOST = os.getenv("INTENT_STUDIO_HOST", "127.0.0.1")
PORT = int(os.getenv("INTENT_STUDIO_PORT", "8000"))

SENSITIVITY_PRESETS: dict[str, dict[str, float]] = {
    # Calibrated on qwen3-embedding:0.6b with the instruction in embeddings.py on real extracted
    # intents: same-intent pairs have a median cosine of ~0.85 (p25 ~0.76); distinct intents in the
    # same L2 have a median of ~0.66 but p95 ~0.78. Embeddings therefore only auto-match at high
    # similarity; uncertain candidates are resolved by the LLM during batch refinement.
    # match: min cosine similarity to an L4 centroid for automatic assignment
    # cluster: min average pairwise similarity for a candidate group
    # merge: centroid similarity above which two categories are flagged as overlapping
    "low": {"match": 0.78, "cluster": 0.68, "merge": 0.86},
    "medium": {"match": 0.82, "cluster": 0.73, "merge": 0.88},
    "high": {"match": 0.86, "cluster": 0.78, "merge": 0.91},
}


@dataclass
class Settings:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    llm_model: str = os.getenv("INTENT_STUDIO_LLM_MODEL", "qwen3:8b")
    embedding_model: str = os.getenv("INTENT_STUDIO_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    batch_size: int = int(os.getenv("INTENT_STUDIO_BATCH_SIZE", "25"))
    clustering_sensitivity: str = os.getenv("INTENT_STUDIO_CLUSTERING_SENSITIVITY", "medium")
    request_timeout: float = float(os.getenv("INTENT_STUDIO_REQUEST_TIMEOUT", "180"))
    auto_accept_new_categories: bool = os.getenv("INTENT_STUDIO_AUTO_ACCEPT", "true").lower() == "true"

    def thresholds(self) -> dict[str, float]:
        return SENSITIVITY_PRESETS.get(self.clustering_sensitivity, SENSITIVITY_PRESETS["medium"])

    def to_dict(self) -> dict:
        return asdict(self)


def coerce_setting(name: str, value):
    """Convert a raw (string or JSON) value to the type of the Settings field."""
    field_types = {f.name: f.type for f in fields(Settings)}
    if name not in field_types:
        raise KeyError(name)
    t = field_types[name]
    if t in ("bool", bool):
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "on")
    if t in ("int", int):
        return int(value)
    if t in ("float", float):
        return float(value)
    return str(value)
