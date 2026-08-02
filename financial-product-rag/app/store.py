from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class DataLoadError(RuntimeError):
    """Raised at startup when a data file is missing or malformed."""


def _load(name: str) -> list[dict[str, Any]]:
    path = DATA_DIR / name
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise DataLoadError(f"required data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"invalid JSON in {path}: {exc}") from exc


@lru_cache(maxsize=1)
def products() -> list[dict[str, Any]]:
    return _load("product_master.json")


@lru_cache(maxsize=1)
def knowledge_articles() -> list[dict[str, Any]]:
    return _load("knowledge_articles.json")


@lru_cache(maxsize=1)
def score_rules() -> list[dict[str, Any]]:
    return _load("recommendation_rules.json")


@lru_cache(maxsize=1)
def sources() -> dict[str, dict[str, Any]]:
    return {s["source_id"]: s for s in _load("source_registry.json")}


@lru_cache(maxsize=1)
def review_queue() -> list[dict[str, Any]]:
    return _load("review_queue.json")


@lru_cache(maxsize=1)
def rag_documents() -> list[dict[str, Any]]:
    """Product/guide text blobs used only by the operator-facing /search
    debugging endpoint (see app/evidence_retriever.py). Not used to decide
    which products get recommended."""
    with (DATA_DIR / "rag_documents.jsonl").open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def validate_on_startup() -> None:
    """Fail fast with a clear error if any data file is missing/malformed.
    Called once at app import time (see app/main.py)."""
    products()
    knowledge_articles()
    score_rules()
    sources()
    review_queue()
    rag_documents()
