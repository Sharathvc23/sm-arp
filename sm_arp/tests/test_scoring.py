"""Conformance for ``sm_arp.vrp`` nanda-rep/0.2 scoring (VRP 0.3 §B-C).

Pins ``reputation_score_v2`` + ``corroboration_rate`` — including collusion
severance — so every resolver computes identical reputation. Golden values are
golden reference output for fixed-seed scenarios.
"""

from __future__ import annotations

from typing import Any

from sm_arp.identity import did_from_sk
from sm_arp.vrp import (
    build_ledger,
    corroboration_rate,
    facet_from_ledger,
    reputation_score,
    reputation_score_v2,
    verify_ledger,
)

_TRUE = lambda _r: True  # noqa: E731 — all receipts ARP-valid; corroboration is what's under test


def _corroborated(issuer_seed: bytes, cp_seed: bytes, rid: str) -> dict[str, Any]:
    from sm_arp.vrp import cosign_receipt

    r = {
        "version": "arp/0.1",
        "receipt_id": rid,
        "issuer_did": did_from_sk(issuer_seed),
        "issued_at": "2026-01-01T00:00:00Z",
        "action": {
            "category": "message_sent",
            "human_summary": "x",
            "outcome": "completed",
            "counterparty_did": did_from_sk(cp_seed),
        },
    }
    r["evidence"] = {"witness_signatures": [cosign_receipt(r, signing_key_bytes=cp_seed)]}
    return r


def _uncorroborated(issuer_seed: bytes, cp_seed: bytes, rid: str) -> dict[str, Any]:
    return {
        "version": "arp/0.1",
        "receipt_id": rid,
        "issuer_did": did_from_sk(issuer_seed),
        "issued_at": "2026-01-01T00:00:00Z",
        "action": {
            "category": "message_sent",
            "human_summary": "x",
            "outcome": "completed",
            "counterparty_did": did_from_sk(cp_seed),
        },
    }


def test_golden_v2_gates_uncorroborated() -> None:
    # A->B corroborated, A->C not. 0.1 counts both; 0.2 counts only the corroborated.
    a, b, c = bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32
    rs = [_corroborated(a, b, "r1"), _uncorroborated(a, c, "r2")]
    assert reputation_score(rs, is_valid=_TRUE) == 2.0
    assert reputation_score_v2(rs, is_valid=_TRUE) == 1.0
    assert corroboration_rate(rs, is_valid=_TRUE) == 0.5


def test_golden_collusion_pair_is_severed() -> None:
    # Honest 3-ring A->B->C->A (anchor) + an isolated mutual pair X<->Y (collusion).
    # The pair is severed: only the 3 honest receipts score (§B).
    a, b, c, x, y = (bytes([i]) * 32 for i in (1, 2, 3, 10, 11))
    ring = [_corroborated(a, b, "ab"), _corroborated(b, c, "bc"), _corroborated(c, a, "ca")]
    pair = [_corroborated(x, y, "xy"), _corroborated(y, x, "yx")]
    rs = ring + pair
    assert reputation_score_v2(rs, is_valid=_TRUE) == 3.0  # pair severed, ring counts
    assert corroboration_rate(rs, is_valid=_TRUE) == 0.6  # 3 effective / 5 valid


def test_empty_corroboration_rate_is_zero() -> None:
    assert corroboration_rate([], is_valid=_TRUE) == 0.0


def test_invalid_receipts_score_zero_under_v2() -> None:
    a, b = bytes([1]) * 32, bytes([2]) * 32
    rs = [_corroborated(a, b, "r")]
    assert reputation_score_v2(rs, is_valid=lambda _r: False) == 0.0


# ── ledger / facet round-trip under nanda-rep/0.2 ────────────────────


def test_ledger_v2_roundtrip() -> None:
    a, b, c = bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32
    rs = [_corroborated(a, b, "r1"), _uncorroborated(a, c, "r2")]
    ledger = build_ledger(
        subject=did_from_sk(a),
        receipts=rs,
        is_valid=_TRUE,
        as_of="2026-01-01T00:00:00Z",
        method="nanda-rep/0.2",
    )
    assert ledger["scoring_method"] == "nanda-rep/0.2"
    assert ledger["reputation_score"] == 1.0
    assert ledger["corroboration_rate"] == 0.5
    assert verify_ledger(ledger, is_valid=_TRUE).ok is True
    facet = facet_from_ledger(ledger, ledger_uri="https://example/ledger")
    assert facet["scoring_method"] == "nanda-rep/0.2"
    assert facet["corroboration_rate"] == 0.5


def test_ledger_v1_unchanged_and_omits_corroboration_rate() -> None:
    # Default method=0.1: backward-compatible, no corroboration_rate anywhere.
    a, b = bytes([1]) * 32, bytes([2]) * 32
    rs = [_corroborated(a, b, "r1")]
    ledger = build_ledger(subject=did_from_sk(a), receipts=rs, is_valid=_TRUE, as_of="t")
    assert ledger["scoring_method"] == "nanda-rep/0.1"
    assert "corroboration_rate" not in ledger
    assert verify_ledger(ledger, is_valid=_TRUE).ok is True
    assert "corroboration_rate" not in facet_from_ledger(ledger, ledger_uri="u")


def test_verify_ledger_detects_tampered_corroboration_rate() -> None:
    a, b, c = bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32
    rs = [_corroborated(a, b, "r1"), _uncorroborated(a, c, "r2")]
    ledger = build_ledger(
        subject=did_from_sk(a), receipts=rs, is_valid=_TRUE, as_of="t", method="nanda-rep/0.2"
    )
    ledger["corroboration_rate"] = 0.99  # tamper
    v = verify_ledger(ledger, is_valid=_TRUE)
    assert v.ok is False and v.stage == "score_mismatch"
