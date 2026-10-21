"""Minimal Ollama REST client (/api/tags, /api/chat, /api/embed).

Error messages raised from this module never contain prompt or transcript content.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger("intent_studio.ollama")

T = TypeVar("T", bound=BaseModel)

# Caps runaway generations (repetition loops) well below the request timeout; the longest
# legitimate answers (outlier decisions for a full chunk) stay far below this.
MAX_OUTPUT_TOKENS = 3000
# Intent statements are one or two sentences; without this, Ollama loads the embedding model with its
# 32k default context and reserves ~5 GB instead of ~1 GB. Longer inputs are truncated.
EMBED_NUM_CTX = 2048


class OllamaError(RuntimeError):
    """Safe-to-display error (no transcript content)."""


class StructuredOutputError(OllamaError):
    pass


def _strip(content: str) -> str:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


def summarize_validation_error(err: ValidationError) -> str:
    parts = []
    for e in err.errors()[:5]:
        loc = ".".join(str(x) for x in e.get("loc", ()))
        parts.append(f"{loc or 'root'}: {e.get('type')}")
    return "; ".join(parts)


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 180.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = self._client.post(path, json=payload)
        except httpx.TimeoutException as e:
            raise OllamaError(f"Ollama request to {path} timed out after {self.timeout:.0f}s") from e
        except httpx.HTTPError as e:
            raise OllamaError(f"Cannot reach Ollama at {self.base_url} ({type(e).__name__})") from e
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = str(resp.json().get("error", ""))[:200]
            except ValueError:
                pass
            raise OllamaError(f"Ollama {path} returned HTTP {resp.status_code}: {detail}")
        try:
            return resp.json()
        except ValueError as e:
            raise OllamaError(f"Ollama {path} returned a non-JSON response") from e

    def tags(self) -> list[dict]:
        try:
            resp = self._client.get("/api/tags", timeout=10.0)
            resp.raise_for_status()
            return resp.json().get("models", [])
        except httpx.HTTPError as e:
            raise OllamaError(f"Cannot reach Ollama at {self.base_url} ({type(e).__name__})") from e

    def chat(self, model: str, messages: list[dict], schema: dict | None = None, temperature: float = 0.0,
             num_ctx: int = 8192, num_predict: int = MAX_OUTPUT_TOKENS) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict, "seed": 42},
        }
        if schema is not None:
            payload["format"] = schema
        # qwen3 supports disabling reasoning; gpt-oss only accepts reasoning levels.
        if model.startswith("gpt-oss"):
            payload["think"] = "low"
        else:
            payload["think"] = False
        data = self._post("/api/chat", payload)
        return (data.get("message") or {}).get("content", "") or ""

    def chat_structured(self, model: str, system: str, user: str, output_model: Type[T],
                        retries: int = 2, temperature: float = 0.0, schema: dict | None = None) -> T:
        """Call the chat API with a JSON schema and validate the answer, retrying with feedback."""
        schema = schema or output_model.model_json_schema()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error = "no response"
        for attempt in range(retries + 1):
            content = self.chat(model, messages, schema=schema, temperature=temperature if attempt == 0 else 0.2)
            cleaned = _strip(content)
            try:
                return output_model.model_validate(json.loads(cleaned))
            except json.JSONDecodeError:
                last_error = "response was not valid JSON"
            except ValidationError as e:
                last_error = summarize_validation_error(e)
            log.warning("Malformed structured output (attempt %d): %s", attempt + 1, last_error)
            messages = messages[:2] + [
                {"role": "assistant", "content": cleaned[:4000]},
                {"role": "user", "content": f"The previous answer did not match the required JSON schema "
                                            f"({last_error}). Answer again with valid JSON only."},
            ]
        raise StructuredOutputError(f"Model output failed validation after {retries + 1} attempts: {last_error}")

    def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        data = self._post("/api/embed", {"model": model, "input": inputs, "truncate": True,
                                         "options": {"num_ctx": EMBED_NUM_CTX}})
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise OllamaError("Ollama /api/embed returned an unexpected number of embeddings")
        return vectors


def connection_test(base_url: str, llm_model: str, embedding_model: str, timeout: float) -> dict:
    """Verify server reachability, real inference and real embedding generation."""
    result: dict[str, Any] = {"ok": False, "server": None, "llm": None, "embedding": None, "models": []}
    with OllamaClient(base_url, timeout=timeout) as client:
        t0 = time.perf_counter()
        try:
            models = client.tags()
        except OllamaError as e:
            result["server"] = {"ok": False, "error": str(e)}
            return result
        names = [m.get("name") or m.get("model") for m in models]
        result["models"] = names
        result["server"] = {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000)}

        class Ping(BaseModel):
            status: str

        t0 = time.perf_counter()
        try:
            out = client.chat_structured(
                llm_model, "You are a health check. Reply in JSON.", 'Return {"status": "ok"}.', Ping, retries=1
            )
            result["llm"] = {"ok": True, "model": llm_model, "reply": out.status[:20],
                             "latency_ms": round((time.perf_counter() - t0) * 1000),
                             "installed": llm_model in names}
        except OllamaError as e:
            result["llm"] = {"ok": False, "model": llm_model, "error": str(e), "installed": llm_model in names}

        t0 = time.perf_counter()
        try:
            vecs = client.embed(embedding_model, ["connection test"])
            result["embedding"] = {"ok": True, "model": embedding_model, "dimensions": len(vecs[0]),
                                   "latency_ms": round((time.perf_counter() - t0) * 1000),
                                   "installed": embedding_model in names}
        except OllamaError as e:
            result["embedding"] = {"ok": False, "model": embedding_model, "error": str(e),
                                   "installed": embedding_model in names}
    result["ok"] = bool(result["server"]["ok"] and result["llm"]["ok"] and result["embedding"]["ok"])
    return result
