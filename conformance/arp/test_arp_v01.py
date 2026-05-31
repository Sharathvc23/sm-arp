"""ARP v0.1 conformance test suite.

Loads every vector in ``vectors/arp/0.1/*.json`` and asserts that running
it through ``verify_receipt`` produces the documented ``expected_outcome``
at the documented stage.

Expected outcomes:
  - ``verify_pass`` — receipt verifies fully (schema + signature, plus
    chain when applicable).
  - ``schema_fail`` — JSON-Schema validation fails (before signature).
  - ``signature_fail`` — schema passes but Ed25519 verification fails.
  - ``hash_chain_fail`` — schema + signature pass but the declared
    previous_receipt_hash does not match the prior under test.

Run::

    pytest conformance/arp/

The harness in ``conformance/arp/__init__.py`` is intentionally
framework-agnostic. This test file is intentionally thin: every assertion
funnels through ``verify_receipt`` so a downstream implementer can
import the same harness with their own vector source if needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conformance.arp import compute_chain_link, verify_receipt

VECTORS_DIR = Path(__file__).resolve().parent.parent.parent / "vectors" / "arp" / "0.1"
ALL_VECTORS = sorted(VECTORS_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


# Map each negative outcome → the verification stage we expect to fail at.
EXPECTED_STAGE = {
    "verify_pass": "accepted",
    "schema_fail": "schema",
    "signature_fail": "signature",
    "hash_chain_fail": "hash_chain",
}


@pytest.fixture(scope="module")
def chain_priors() -> dict[str, dict]:
    """Build the prior-receipt lookup for hash-chain tests.

    Vector 12 declares previous_receipt_hash pointing at vector 11; we
    pre-compute that link so verify_receipt can resolve the chain.
    """
    priors: dict[str, dict] = {}
    for path in ALL_VECTORS:
        v = _load(path)
        receipt = v["receipt"]
        if v["expected_outcome"] != "verify_pass":
            continue
        link = compute_chain_link(receipt)
        priors[link] = receipt
    return priors


@pytest.mark.parametrize(
    "vector_path",
    ALL_VECTORS,
    ids=lambda p: p.stem,
)
def test_vector_matches_expected_outcome(vector_path: Path, chain_priors: dict[str, dict]) -> None:
    v = _load(vector_path)
    expected_outcome = v["expected_outcome"]
    expected_stage = EXPECTED_STAGE.get(expected_outcome)
    assert expected_stage is not None, (
        f"vector {v['id']} has unknown expected_outcome={expected_outcome!r}"
    )

    mode = v.get("verifier_mode", "strict")
    result = verify_receipt(v["receipt"], mode=mode, prior_receipts=chain_priors)

    if expected_outcome == "verify_pass":
        assert result.ok, f"{v['id']}: expected pass, got {result.stage}: {result.detail}"
        assert result.stage == "accepted"
    else:
        assert not result.ok, (
            f"{v['id']}: expected fail at stage {expected_stage}, "
            f"but verification passed: {result.detail}"
        )
        assert result.stage == expected_stage, (
            f"{v['id']}: expected failure at stage {expected_stage}, "
            f"got {result.stage}: {result.detail}"
        )


def test_at_least_20_vectors_present() -> None:
    """Spec promises 20+ vectors; this protects against accidental deletion."""
    assert len(ALL_VECTORS) >= 20, f"only {len(ALL_VECTORS)} vectors found"


def test_every_positive_vector_has_unique_receipt_id() -> None:
    """Two distinct positive vectors must not share a receipt_id (within issuer)."""
    seen: dict[tuple[str, str], str] = {}
    for path in ALL_VECTORS:
        v = _load(path)
        if v["expected_outcome"] != "verify_pass":
            continue
        r = v["receipt"]
        key = (r["issuer_did"], r["receipt_id"])
        if key in seen:
            raise AssertionError(f"vector {v['id']} shares receipt_id with {seen[key]}: {key}")
        seen[key] = v["id"]


def test_hash_chain_link_recomputable() -> None:
    """Vector 12's previous_receipt_hash MUST equal compute_chain_link(vector 11's receipt)."""
    v11 = _load(VECTORS_DIR / "11-chain-genesis.json")
    v12 = _load(VECTORS_DIR / "12-chain-linked.json")
    expected = compute_chain_link(v11["receipt"])
    declared = v12["receipt"]["previous_receipt_hash"]
    assert declared == expected, f"vector 12 declares {declared} but recomputed link is {expected}"
