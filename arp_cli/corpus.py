"""Vector corpus loader for the ARP CLI.

Finds the in-repo golden vectors at ``vectors/arp/0.1/`` and knows which
subset to feature in the demo. Other commands accept arbitrary file paths;
this module is for the curated-corpus operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from conformance.arp import compute_chain_link


# The CLI resolves the corpus by walking up from this file's location until
# it finds a "vectors/arp/0.1" directory. This works whether the package is
# installed (-e) from the repo root or run from a checkout.
def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "vectors" / "arp" / "0.1").is_dir():
            return parent
    raise FileNotFoundError(
        "Could not locate vectors/arp/0.1/ relative to arp_cli. "
        "Run from a sm-arp checkout or install the package in editable mode."
    )


REPO_ROOT = _find_repo_root()
VECTORS_DIR = REPO_ROOT / "vectors" / "arp" / "0.1"
NANDA_TRACE = REPO_ROOT / "nanda" / "nanda_interaction_trace.json"


@dataclass(frozen=True)
class VectorMeta:
    vector_id: str
    description: str
    expected_outcome: str  # verify_pass | schema_fail | signature_fail | hash_chain_fail
    verifier_mode: str  # strict | tolerant
    path: Path

    def load(self) -> dict:
        return json.loads(self.path.read_text())


def list_vectors() -> list[VectorMeta]:
    """Every golden vector in the corpus, sorted by filename."""
    out: list[VectorMeta] = []
    for p in sorted(VECTORS_DIR.glob("*.json")):
        v = json.loads(p.read_text())
        out.append(
            VectorMeta(
                vector_id=v["id"],
                description=v["description"],
                expected_outcome=v["expected_outcome"],
                verifier_mode=v.get("verifier_mode", "strict"),
                path=p,
            )
        )
    return out


def get_vector(vector_id: str) -> VectorMeta:
    """Look up a vector by its id (e.g. '01-basic-purchase')."""
    for v in list_vectors():
        if v.vector_id == vector_id:
            return v
    raise KeyError(f"unknown vector {vector_id!r} — run `arp vectors list` to see all")


def chain_priors() -> dict[str, dict]:
    """Map previous_receipt_hash value → prior receipt, built over the positive corpus.

    Same pattern the conformance test fixture uses (test_arp_v01.py). Lets
    `verify_receipt(..., prior_receipts=chain_priors())` resolve hash-chain
    links automatically for any vector whose predecessor is in the corpus.
    """
    priors: dict[str, dict] = {}
    for meta in list_vectors():
        if meta.expected_outcome != "verify_pass":
            continue
        receipt = meta.load()["receipt"]
        priors[compute_chain_link(receipt)] = receipt
    return priors


# ── the demo spine ─────────────────────────────────────────────────
#
# Seven vectors chosen so every distinctive ARP feature appears once.
# Order is the order they appear in `arp demo`; the blurb is what the
# CLI prints between steps.

DEMO_SPINE: list[tuple[str, str]] = [
    (
        "01-basic-purchase",
        "the minimum viable receipt — required fields plus a counterparty and amount.",
    ),
    (
        "16-invalid-signature",
        "tamper detection — body altered after signing; Ed25519 rejects it.",
    ),
    (
        "12-chain-linked",
        "tamper-evident hash chain over time — previous_receipt_hash links back to a prior receipt.",
    ),
    (
        "04-data-shared-gdpr",
        "regulatory-grade evidence — jurisdiction, multilingual summary, requires_review.",
    ),
    (
        "15-with-tool-invocations",
        "MCP integration — hashes of tool request/response preserve audit without leaking content.",
    ),
    (
        "22-unknown-category-tolerant",
        "forward compatibility — unknown extensions and categories preserved, not rejected.",
    ),
    (
        "nanda_interaction_trace",  # sentinel: handled specially (it's a trace file, not a vector)
        "cross-principal authority graph — Receipt 3 -> Receipt 2 -> Receipt 1 walks back to the human.",
    ),
]
