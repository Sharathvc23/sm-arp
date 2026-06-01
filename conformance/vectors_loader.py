"""Loads JSON test vectors from the vectors/ directory.

Vectors are language-agnostic JSON files that define the protocol's expected
inputs and outputs. Every conformance test loads vectors via this module so
the path resolution lives in one place.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

VECTORS_ROOT = Path(__file__).resolve().parent.parent / "vectors"


@cache
def load(*path_parts: str) -> dict[str, Any]:
    """Load a vector file by path components relative to vectors/.

    Example:
        load("signing", "did-key-derivations.json")
    """
    path = VECTORS_ROOT.joinpath(*path_parts)
    if not path.exists():
        raise FileNotFoundError(f"Vector file not found: {path} (resolved from {VECTORS_ROOT})")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def cases(vector: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the 'cases' list from a vector file. Empty list if absent."""
    return vector.get("cases", []) or []


def adversarial_cases(vector: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the 'adversarial_cases' list. Empty list if absent."""
    return vector.get("adversarial_cases", []) or []
