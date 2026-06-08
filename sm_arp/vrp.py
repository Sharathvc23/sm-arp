"""Verifiable Receipts Profile (VRP 0.1).

The receipt + ledger commitment + scoring primitives that compose ARP receipts
into a portable, reputation-aware credential: the ``behavioral_merkle_root``, the
``nanda-rep/0.1`` scoring method, and the Receipts Ledger object. Deterministic —
any party (issuer, verifier, resolver) recomputes the same root and score.

CRITICAL: ``behavioral_merkle_root`` here is NOT an RFC 6962 inclusion-proof tree;
the two are different commitments and MUST NEVER be interchanged:

  * an RFC 6962 tree uses domain-separated leaf/node hashes (0x00 / 0x01) with odd
    nodes promoted — for inclusion/consistency proofs over an append-only log.
  * ``behavioral_merkle_root`` (here) uses plain SHA-256 of the JCS bytes for
    leaves and plain SHA-256(left||right) for nodes, with odd nodes DUPLICATED —
    the commitment a resolver recomputes from a published Receipts Ledger.

Purity: nothing here imports the ARP verifier. "A receipt is valid" is supplied
by the caller as an ``is_valid`` callable, so this module composes with any
verifier without a cross-package import.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import jcs

SCORING_METHOD = "nanda-rep/0.1"
LEDGER_MEDIA_TYPE = "application/vnd.nanda.receipts-ledger+json"

# nanda-rep/0.1 per-category weights (published as part of the scoring method).
# Consequential actions count for more than routine ones; administrative/governance
# categories are reputation-neutral; a breached commitment earns nothing.
DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    # financial / high-consequence
    "purchase": 5.0,
    "payment_sent": 5.0,
    "payment_received": 5.0,
    # commitments
    "commitment_entered": 4.0,
    "commitment_fulfilled": 4.0,
    "commitment_breached": 0.0,
    # attestations / governance-bearing
    "attestation_issued": 2.0,
    "attestation_received": 2.0,
    "vote_cast": 2.0,
    "decision_made": 2.0,
    "data_shared": 2.0,
    # routine
    "message_sent": 1.0,
    "message_received": 1.0,
    "appointment_booked": 1.0,
    "appointment_cancelled": 1.0,
    "subscription_changed": 1.0,
    "record_filed": 1.0,
    "account_created": 1.0,
    "account_closed": 1.0,
    # administrative — reputation-neutral
    "authority_granted": 0.0,
    "authority_revoked": 0.0,
    "other": 0.0,
}


# ── behavioral Merkle root ───────────────────────────


def _ordered_leaf_hashes(receipts: Sequence[dict[str, Any]]) -> list[bytes]:
    """Leaf hashes in the canonical order: by ``issued_at`` then ``receipt_id``
    ascending. Each leaf = SHA-256 of the receipt's JCS bytes INCLUDING its
    signature."""
    ordered = sorted(receipts, key=lambda r: (r.get("issued_at", ""), r.get("receipt_id", "")))
    return [hashlib.sha256(jcs.canonicalize(r)).digest() for r in ordered]


def behavioral_merkle_root(receipts: Sequence[dict[str, Any]]) -> str | None:
    """The ``sha256:<hex>`` commitment over ``receipts``.

    Plain binary Merkle tree: node = SHA-256(left || right); at any level with an
    odd count, the final node is DUPLICATED. Returns None for an empty ledger
    (its facet SHOULD be omitted). A single receipt's root is its leaf hash.
    """
    level = _ordered_leaf_hashes(receipts)
    if not level:
        return None
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = [*level, level[-1]]  # duplicate the final node
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return "sha256:" + level[0].hex()


# ── nanda-rep/0.1 scoring ────────────────────────────

IsValid = Callable[[dict[str, Any]], bool]


def validity_rate(receipts: Sequence[dict[str, Any]], *, is_valid: IsValid) -> float:
    """Fraction (0.0-1.0) of receipts that verify under their stated rules.
    Empty ledger -> 0.0."""
    if not receipts:
        return 0.0
    valid = sum(1 for r in receipts if is_valid(r))
    return valid / len(receipts)


def reputation_score(
    receipts: Sequence[dict[str, Any]],
    *,
    is_valid: IsValid,
    weights: dict[str, float] = DEFAULT_CATEGORY_WEIGHTS,
) -> float:
    """Sum of per-category weights over the VALID receipts. Reproducible
    by anyone with the ledger + this weight table."""
    total = 0.0
    for r in receipts:
        if is_valid(r):
            category = (r.get("action") or {}).get("category", "")
            total += weights.get(category, 0.0)
    return total


# ── Receipts Ledger ────────────────────────────────────


def build_ledger(
    *,
    subject: str,
    receipts: Sequence[dict[str, Any]],
    is_valid: IsValid,
    as_of: str,
    weights: dict[str, float] = DEFAULT_CATEGORY_WEIGHTS,
    inline: bool = True,
) -> dict[str, Any]:
    """Assemble a ``application/vnd.nanda.receipts-ledger+json`` document.

    Self-describing: carries the root + derived scores so a resolver can both
    recompute and detect divergence. ``as_of`` is caller-supplied (this module
    takes no wall-clock). With ``inline=False`` the
    receipts are emitted as ``{receipt_id, receipt_hash}`` references.
    """
    root = behavioral_merkle_root(receipts)
    if inline:
        receipts_field: list[dict[str, Any]] = list(receipts)
    else:
        receipts_field = [
            {
                "receipt_id": r.get("receipt_id"),
                "receipt_hash": "sha256:" + hashlib.sha256(jcs.canonicalize(r)).hexdigest(),
            }
            for r in receipts
        ]
    ledger: dict[str, Any] = {
        "subject": subject,
        "scoring_method": SCORING_METHOD,
        "behavioral_merkle_root": root,
        "reputation_score": reputation_score(receipts, is_valid=is_valid, weights=weights),
        "validity_rate": validity_rate(receipts, is_valid=is_valid),
        "receipt_count": len(receipts),
        "as_of": as_of,
        "receipts": receipts_field,
    }
    return ledger


def facet_from_ledger(
    ledger: dict[str, Any],
    *,
    ledger_uri: str,
    attested_by: str | None = None,
) -> dict[str, Any]:
    """Project a Receipts Ledger into the AgentFacts ``verifiable_receipts`` facet
    - the lightweight pointer published in discovery metadata."""
    facet: dict[str, Any] = {
        "ledger_uri": ledger_uri,
        "ledger_media_type": LEDGER_MEDIA_TYPE,
        "behavioral_merkle_root": ledger.get("behavioral_merkle_root"),
        "receipt_count": ledger.get("receipt_count"),
        "reputation_score": ledger.get("reputation_score"),
        "validity_rate": ledger.get("validity_rate"),
        "scoring_method": ledger.get("scoring_method", SCORING_METHOD),
        "as_of": ledger.get("as_of"),
    }
    if attested_by is not None:
        facet["attested_by"] = attested_by
    return facet


@dataclass
class LedgerVerification:
    ok: bool
    stage: str  # root_mismatch | score_mismatch | count_mismatch | not_recomputable | accepted
    detail: str

    @classmethod
    def accepted(cls) -> LedgerVerification:
        return cls(True, "accepted", "ledger recomputes to its published values")


def verify_ledger(
    ledger: dict[str, Any],
    *,
    is_valid: IsValid,
    weights: dict[str, float] = DEFAULT_CATEGORY_WEIGHTS,
    score_tolerance: float = 1e-9,
) -> LedgerVerification:
    """Recompute the root + nanda-rep values from the ledger's inline receipts and
    confirm they match the published values.

    A resolver SHOULD reject/down-rank a ledger whose recomputed values diverge.
    Requires inline receipts; a ref-only ledger is ``not_recomputable`` here (the
    caller must fetch the receipts first).
    """
    receipts = ledger.get("receipts")
    if not isinstance(receipts, list) or any("action" not in r for r in receipts):
        return LedgerVerification(False, "not_recomputable", "ledger receipts are not inline")

    declared = ledger.get("receipt_count")
    if declared != len(receipts):
        return LedgerVerification(False, "count_mismatch", f"count {declared} != {len(receipts)}")

    recomputed_root = behavioral_merkle_root(receipts)
    if recomputed_root != ledger.get("behavioral_merkle_root"):
        return LedgerVerification(False, "root_mismatch", "recomputed root differs from published")

    recomputed_score = reputation_score(receipts, is_valid=is_valid, weights=weights)
    if abs(recomputed_score - float(ledger.get("reputation_score", 0))) > score_tolerance:
        return LedgerVerification(False, "score_mismatch", "recomputed reputation_score differs")

    recomputed_validity = validity_rate(receipts, is_valid=is_valid)
    if abs(recomputed_validity - float(ledger.get("validity_rate", 0))) > score_tolerance:
        return LedgerVerification(False, "score_mismatch", "recomputed validity_rate differs")

    return LedgerVerification.accepted()


__all__ = [
    "DEFAULT_CATEGORY_WEIGHTS",
    "LEDGER_MEDIA_TYPE",
    "SCORING_METHOD",
    "LedgerVerification",
    "behavioral_merkle_root",
    "build_ledger",
    "facet_from_ledger",
    "reputation_score",
    "validity_rate",
    "verify_ledger",
]
