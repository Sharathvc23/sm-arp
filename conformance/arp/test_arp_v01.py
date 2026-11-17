"""ARP v0.1 conformance test suite.

Loads every vector in ``vectors/arp/0.1/*.json`` and asserts that running
it through ``verify_receipt`` produces the documented ``expected_outcome``
at the documented stage.

Expected outcomes:
  - ``verify_pass`` — receipt verifies fully (schema + signature, plus
    chain when applicable).
  - ``schema_fail`` — JSON-Schema validation fails (before signature).
  - ``signature_fail`` — schema passes but Ed25519 verification fails.
  - ``freshness_fail`` — schema + signature pass but ``issued_at`` is outside
    the default ±300 s window around the vector's ``verifier_now``.
  - ``reversal_fail`` — schema + signature pass but the reversal's issuer is
    not the issuer of the original it reverses (the positive corpus is the set
    of originals the verifier holds).
  - ``hash_chain_fail`` — schema + signature pass but the declared
    previous_receipt_hash does not match the prior under test.

A vector that carries ``verifier_now`` is verified as a live event at that
instant; a vector without one is verified after the fact (no freshness window).

Run::

    pytest conformance/arp/

The harness in ``conformance/arp/__init__.py`` is intentionally
framework-agnostic. This test file is intentionally thin: every assertion
funnels through ``verify_receipt`` so a downstream implementer can
import the same harness with their own vector source if needed.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance.arp import (
    compute_chain_link,
    verify_freshness,
    verify_receipt,
    verify_reversal,
)

VECTORS_DIR = Path(__file__).resolve().parent.parent.parent / "vectors" / "arp" / "0.1"
ALL_VECTORS = sorted(VECTORS_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


# Map each negative outcome → the verification stage we expect to fail at.
EXPECTED_STAGE = {
    "verify_pass": "accepted",
    "schema_fail": "schema",
    "signature_fail": "signature",
    "freshness_fail": "freshness",
    "reversal_fail": "reversal",
    "hash_chain_fail": "hash_chain",
}


def _verifier_now(v: dict) -> datetime | None:
    """The vector's reference instant for the §3.3 window, or None (after the fact)."""
    raw = v.get("verifier_now")
    return datetime.fromisoformat(raw) if raw else None


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


@pytest.fixture(scope="module")
def corpus_originals() -> dict[str, dict]:
    """The receipts the verifier holds for the §4.2 reversal check: every positive
    vector, keyed by receipt_id (vector 10 and 29 both reverse vector 01)."""
    return {
        v["receipt"]["receipt_id"]: v["receipt"]
        for v in map(_load, ALL_VECTORS)
        if v["expected_outcome"] == "verify_pass"
    }


@pytest.mark.parametrize(
    "vector_path",
    ALL_VECTORS,
    ids=lambda p: p.stem,
)
def test_vector_matches_expected_outcome(
    vector_path: Path, chain_priors: dict[str, dict], corpus_originals: dict[str, dict]
) -> None:
    v = _load(vector_path)
    expected_outcome = v["expected_outcome"]
    expected_stage = EXPECTED_STAGE.get(expected_outcome)
    assert expected_stage is not None, (
        f"vector {v['id']} has unknown expected_outcome={expected_outcome!r}"
    )

    mode = v.get("verifier_mode", "strict")
    result = verify_receipt(
        v["receipt"],
        mode=mode,
        prior_receipts=chain_priors,
        originals=corpus_originals,
        now=_verifier_now(v),
    )

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


def test_unknown_verifier_mode_is_rejected() -> None:
    """A mode other than strict/tolerant used to behave as tolerant silently."""
    v = _load(VECTORS_DIR / "01-basic-purchase.json")
    with pytest.raises(ValueError, match="unknown verifier mode"):
        verify_receipt(v["receipt"], mode="lenient")


def test_witness_appended_after_issuance_does_not_move_the_chain_link() -> None:
    """Spec §6.4: the chain link detaches ``evidence.witness_signatures``, so vector
    23's link equals the link of the same receipt with its witnesses removed."""
    v23 = _load(VECTORS_DIR / "23-witnessed-receipt.json")["receipt"]
    stripped = json.loads(json.dumps(v23))
    del stripped["evidence"]["witness_signatures"]
    assert compute_chain_link(v23) == compute_chain_link(stripped)


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


# ── freshness (spec §3.3) and reversal issuer (spec §4.2) ──────────────────


def test_freshness_vectors_verify_after_the_fact() -> None:
    """Without a reference instant no window applies: vectors 26 and 27 are only
    stale / forward-dated relative to their verifier_now, and verify for audit."""
    for name in ("26-stale-issued-at", "27-forward-dated-issued-at"):
        assert verify_receipt(_load(VECTORS_DIR / f"{name}.json")["receipt"]).ok, name


def test_reversal_vector_passes_when_the_original_is_not_held() -> None:
    """§4.2 is enforced against an original the verifier holds. Vector 29 verifies on
    its own (its signature is fine) and fails once vector 01 is held."""
    v29 = _load(VECTORS_DIR / "29-reversal-issuer-mismatch.json")["receipt"]
    v01 = _load(VECTORS_DIR / "01-basic-purchase.json")["receipt"]
    assert verify_receipt(v29).ok
    assert verify_receipt(v29, originals={}).ok
    res = verify_receipt(v29, originals={v01["receipt_id"]: v01})
    assert (res.ok, res.stage) == (False, "reversal")


def test_freshness_window_is_inclusive_and_symmetric() -> None:
    r = _load(VECTORS_DIR / "01-basic-purchase.json")["receipt"]
    issued = datetime.fromisoformat(r["issued_at"])
    for offset, ok in ((-300, True), (300, True), (-301, False), (301, False), (0, True)):
        res = verify_freshness(r, now=issued + timedelta(seconds=offset))
        assert res.ok is ok, (offset, res)
    assert verify_freshness(r, now=issued + timedelta(seconds=10), max_skew_seconds=0).ok is False


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"now": datetime(2026, 5, 21, 14, 23, 1)}, "timezone-aware"),
        ({"now": "2026-05-21T14:23:01Z"}, "timezone-aware"),
        ({"now": datetime.now(UTC), "max_skew_seconds": -1}, "non-negative int"),
        ({"now": datetime.now(UTC), "max_skew_seconds": True}, "non-negative int"),
        ({"now": datetime.now(UTC), "max_skew_seconds": float("nan")}, "non-negative int"),
        ({"max_skew_seconds": 60}, "without now"),
    ],
)
def test_freshness_arguments_that_would_mislead_raise(kwargs: dict, match: str) -> None:
    r = _load(VECTORS_DIR / "01-basic-purchase.json")["receipt"]
    with pytest.raises(ValueError, match=match):
        verify_receipt(r, **kwargs)


def test_freshness_rejects_unparseable_issued_at_without_raising() -> None:
    now = datetime.now(UTC)
    for bad in ("", "yesterday", "2026-05-21T14:23:01", None, 1716301381, ["x"]):
        res = verify_freshness({"issued_at": bad}, now=now)
        assert (res.ok, res.stage) == (False, "freshness"), bad


def _other_signed(receipt: dict, *, receipt_id: str | None = None) -> dict:
    """Re-sign ``receipt`` under a fresh key (a different issuer)."""
    from conformance.arp._vector_gen import did_key_from_pubkey, sign_receipt

    sk = Ed25519PrivateKey.generate()
    out = json.loads(json.dumps(receipt))
    out["issuer_did"] = did_key_from_pubkey(sk.public_key().public_bytes_raw())
    if receipt_id is not None:
        out["receipt_id"] = receipt_id
    return sign_receipt(sk, out)


def test_reversal_hostile_inputs() -> None:
    v01 = _load(VECTORS_DIR / "01-basic-purchase.json")["receipt"]
    v10 = _load(VECTORS_DIR / "10-reversal.json")["receipt"]
    rid = v01["receipt_id"]
    # Same issuer: passes.
    assert verify_reversal(v10, {rid: v01}).ok
    # Index key that is not the original's own receipt_id.
    assert not verify_reversal(v10, {rid: {**v01, "receipt_id": "x"}}).ok
    # A held original whose signature does not verify (tampered after signing).
    tampered = json.loads(json.dumps(v01))
    tampered["action"]["human_summary"] = "Bought 200 tickets."
    res = verify_reversal(v10, {rid: tampered})
    assert (res.ok, res.stage) == (False, "reversal") and "signature" in res.detail
    # An original forged to look like it came from the reversal's issuer: the
    # signature binds issuer_did, so relabelling it fails authentication.
    relabelled = {**v01, "issuer_did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"}
    assert not verify_reversal(v10, {rid: relabelled}).ok
    # Not a receipt object, and a non-string / empty reference.
    assert not verify_reversal(v10, {rid: ["not", "a", "receipt"]}).ok
    for bad in (["x"], {"id": rid}, "", 7, None):
        r = json.loads(json.dumps(v10))
        r["action"]["reversal_of_receipt_id"] = bad
        assert not verify_reversal(r, {rid: v01}).ok, bad
    # A receipt that names itself as the receipt it reverses.
    selfish = json.loads(json.dumps(v10))
    selfish["action"]["reversal_of_receipt_id"] = selfish["receipt_id"]
    assert not verify_reversal(selfish, {selfish["receipt_id"]: selfish}).ok
    # The same reversal re-signed by another agent, with the original held.
    foreign = _other_signed(v10)
    res = verify_receipt(foreign, originals={rid: v01})
    assert (res.ok, res.stage) == (False, "reversal")
    # Original held under a different issuer that legitimately reuses the
    # receipt_id (§3.3 allows it): the verifier's original is that receipt, so the
    # reversal fails. Issuer-scoped ids mean the held original decides.
    same_id_elsewhere = _other_signed(v01)
    assert not verify_reversal(v10, {rid: same_id_elsewhere}).ok


def test_reversal_vector_ships_the_key_of_its_issuer() -> None:
    """Vector 29's private_keys.other_issuer rebuilds its issuer_did, so a verifier
    can build variants of it."""
    from conformance.arp._vector_gen import did_key_from_pubkey

    v29 = _load(VECTORS_DIR / "29-reversal-issuer-mismatch.json")
    seed = base64.b64decode(v29["private_keys"]["other_issuer"])
    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    assert did_key_from_pubkey(pub) == v29["receipt"]["issuer_did"]
    v01 = _load(VECTORS_DIR / "01-basic-purchase.json")["receipt"]
    assert v29["receipt"]["issuer_did"] != v01["issuer_did"]
