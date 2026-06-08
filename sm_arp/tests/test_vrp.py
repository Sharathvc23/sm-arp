"""Conformance for sm_arp.vrp — behavioral_merkle_root, nanda-rep/0.1, Receipts Ledger.

Locks the commitment + scoring so every consumer (sm-rep and other resolvers)
recomputes identical values.
"""

from __future__ import annotations

import hashlib
from typing import Any

import jcs

from sm_arp import Identity, build_action, issue_receipt
from sm_arp.vrp import (
    DEFAULT_CATEGORY_WEIGHTS,
    behavioral_merkle_root,
    build_ledger,
    facet_from_ledger,
    reputation_score,
    validity_rate,
    verify_ledger,
)

SUBJECT = "did:key:zSubjectExample"


def _r(n: int, category: str = "purchase") -> dict[str, Any]:
    return {
        "version": "arp/0.1",
        "receipt_id": f"{n:08d}-1111-4111-8111-111111111111",
        "issuer_did": SUBJECT,
        "principal_did": SUBJECT,
        "issued_at": f"2026-06-07T00:00:0{n}Z",
        "action": {"category": category, "human_summary": f"a{n}", "outcome": "completed"},
        "signature": "AA==",
    }


def _always(_r: dict[str, Any]) -> bool:
    return True


# ── behavioral_merkle_root ──
def test_empty_has_no_root() -> None:
    assert behavioral_merkle_root([]) is None


def test_single_leaf_is_leaf_hash() -> None:
    r = _r(1)
    assert behavioral_merkle_root([r]) == "sha256:" + hashlib.sha256(jcs.canonicalize(r)).hexdigest()


def test_order_independent() -> None:
    rs = [_r(i) for i in range(5)]
    assert behavioral_merkle_root(rs) == behavioral_merkle_root(list(reversed(rs)))


def test_tamper_changes_root() -> None:
    rs = [_r(i) for i in range(3)]
    root = behavioral_merkle_root(rs)
    rs[1]["action"]["human_summary"] = "x"
    assert behavioral_merkle_root(rs) != root


def test_odd_count() -> None:
    rs = [_r(i) for i in range(3)]
    assert behavioral_merkle_root(rs).startswith("sha256:")


# ── nanda-rep/0.1 ──
def test_validity_rate() -> None:
    rs = [_r(i) for i in range(4)]
    assert validity_rate(rs, is_valid=lambda r: r["receipt_id"] != rs[0]["receipt_id"]) == 0.75


def test_weighted_score() -> None:
    rs = [_r(0, "purchase"), _r(1, "payment_sent"), _r(2, "message_sent")]
    assert reputation_score(rs, is_valid=_always) == 11.0


def test_weights_cover_categories() -> None:
    assert {"purchase", "message_sent", "authority_granted", "other"} <= set(DEFAULT_CATEGORY_WEIGHTS)


# ── Receipts Ledger ──
def test_build_then_verify() -> None:
    rs = [_r(i, "purchase") for i in range(3)]
    ledger = build_ledger(subject=SUBJECT, receipts=rs, is_valid=_always, as_of="2026-06-07T00:00:00Z")
    assert ledger["receipt_count"] == 3 and ledger["reputation_score"] == 15.0
    assert verify_ledger(ledger, is_valid=_always).ok


def test_verify_detects_tamper() -> None:
    rs = [_r(i) for i in range(3)]
    ledger = build_ledger(subject=SUBJECT, receipts=rs, is_valid=_always, as_of="2026-06-07T00:00:00Z")
    ledger["receipts"][1]["action"]["human_summary"] = "x"
    assert verify_ledger(ledger, is_valid=_always).stage == "root_mismatch"


def test_verify_detects_count_inflation() -> None:
    rs = [_r(i) for i in range(3)]
    ledger = build_ledger(subject=SUBJECT, receipts=rs, is_valid=_always, as_of="2026-06-07T00:00:00Z")
    ledger["receipt_count"] = 99
    assert verify_ledger(ledger, is_valid=_always).stage == "count_mismatch"


def test_validity_over_real_arp_verifier() -> None:
    sk = Identity.from_seed(hashlib.sha256(b"vrp-real").digest())
    from sm_arp import verify_receipt

    good = [issue_receipt(sk, principal_did=sk.did, action=build_action(category="purchase", human_summary="g")) for _ in range(2)]
    bad = issue_receipt(sk, principal_did=sk.did, action=build_action(category="purchase", human_summary="b"))
    bad["action"]["human_summary"] = "tampered"
    rs = [*good, bad]
    assert abs(validity_rate(rs, is_valid=lambda r: verify_receipt(r).ok) - (2 / 3)) < 1e-9


def test_facet_is_contents_free() -> None:
    ledger = build_ledger(subject=SUBJECT, receipts=[_r(0)], is_valid=_always, as_of="2026-06-07T00:00:00Z")
    facet = facet_from_ledger(ledger, ledger_uri="https://x")
    assert "receipts" not in facet and facet["scoring_method"] == "nanda-rep/0.1"
