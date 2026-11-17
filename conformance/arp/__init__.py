"""ARP v0.1 conformance harness.

Public entry points:

    verify_receipt(receipt: dict, *, mode: str = "strict", prior_receipts=None,
                   originals=None, now=None, max_skew_seconds=None) -> VerificationResult

Loads JSON Schemas with $ref resolution, validates the receipt envelope,
verifies the Ed25519 signature against canonicalized bytes, and then, each only
when the caller supplies the context it needs: ``issued_at`` freshness against a
reference instant (``now``, spec §3.3), a reversal's issuer against the original
it reverses (``originals``, spec §4.2), and the hash chain (``prior_receipts``,
spec §6.4; ``compute_chain_link(prior_receipt)`` gives the link).

The harness is intentionally framework-agnostic: nothing in this package
imports any runtime-specific modules. Any ARP implementation can
run these vectors against its own emit pipeline by importing
``verify_receipt`` from here.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import jcs
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schema" / "arp" / "0.1"


# ── public types ───────────────────────────────────────────────────


@dataclass
class VerificationResult:
    """Outcome of verifying one receipt.

    The ``stage`` field names the stage at which verification reached a
    decision — useful for asserting against negative-vector expectations
    (e.g., expect ``schema`` failure for a malformed receipt rather than
    a ``signature`` failure).
    """

    ok: bool
    stage: str  # one of: schema, signature, freshness, reversal, hash_chain, accepted
    detail: str

    @classmethod
    def accepted(cls) -> VerificationResult:
        return cls(ok=True, stage="accepted", detail="receipt verifies")


# ── schema loading + ref resolution ────────────────────────────────


def _load_registry() -> Registry:
    """Build a referencing.Registry that resolves the ARP schema $refs.

    Schemas reference each other by relative filename (action.schema.json,
    common.schema.json, etc.). The registry maps each filename onto its
    canonical $id so cross-file $refs resolve cleanly.
    """
    registry: Registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text())
        # The $id is the canonical IRI; we also alias the bare filename so
        # in-file $refs like {"$ref": "action.schema.json"} resolve.
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        registry = registry.with_resource(uri=schema["$id"], resource=resource)
        registry = registry.with_resource(uri=path.name, resource=resource)
    return registry


_REGISTRY = _load_registry()
_RECEIPT_SCHEMA = json.loads((SCHEMA_DIR / "receipt.schema.json").read_text())
_VALIDATOR = Draft202012Validator(_RECEIPT_SCHEMA, registry=_REGISTRY)


# ── core verification ──────────────────────────────────────────────


VERIFIER_MODES = ("strict", "tolerant")
DEFAULT_MAX_SKEW_SECONDS = 300  # spec §3.3 default accept window


def _detach_witnesses(receipt: dict[str, Any]) -> dict[str, Any]:
    """The receipt without ``evidence.witness_signatures`` (spec §5, §6.1), dropping
    an ``evidence`` object the removal leaves empty. Witness co-signatures are
    detached evidence appended by third parties after issuance: they are outside
    the issuer's signature and outside the hash chain. Never mutates its input."""
    body = dict(receipt)
    evidence = body.get("evidence")
    if isinstance(evidence, dict) and "witness_signatures" in evidence:
        evidence = {k: v for k, v in evidence.items() if k != "witness_signatures"}
        if evidence:
            body["evidence"] = evidence
        else:
            del body["evidence"]
    return body


def _canonical_bytes_for_signing(receipt: dict[str, Any]) -> bytes:
    """JCS-canonical bytes of the receipt with the signature field removed and the
    witness evidence detached (spec §6.1)."""
    body = _detach_witnesses(receipt)
    body.pop("signature", None)
    return jcs.canonicalize(body)


def _pubkey_from_did(did_key: str) -> Ed25519PublicKey:
    """Decode a did:key string into an Ed25519PublicKey.

    Expects the multibase-z-base58btc form over multicodec 0xed01 || pubkey32.
    """
    import base58

    if not did_key.startswith("did:key:z"):
        raise ValueError(f"Unsupported DID method: {did_key!r}")
    body = did_key[len("did:key:z") :]
    decoded = base58.b58decode(body)
    if len(decoded) != 34 or decoded[:2] != b"\xed\x01":
        raise ValueError("Not a did:key Ed25519 record")
    pubkey32 = decoded[2:]
    return Ed25519PublicKey.from_public_bytes(pubkey32)


def verify_signature(receipt: dict[str, Any]) -> VerificationResult:
    """Verify the Ed25519 signature over canonical bytes (no schema check)."""
    sig_b64 = receipt.get("signature", "")
    issuer_did = receipt.get("issuer_did", "")
    if not sig_b64 or not issuer_did:
        return VerificationResult(False, "signature", "missing signature or issuer_did")
    try:
        pubkey = _pubkey_from_did(issuer_did)
    except Exception as e:
        return VerificationResult(False, "signature", f"invalid issuer_did: {e}")

    try:
        sig_bytes = base64.b64decode(sig_b64, validate=True)
    except Exception as e:
        return VerificationResult(False, "signature", f"signature base64 decode failed: {e}")

    if len(sig_bytes) != 64:
        return VerificationResult(False, "signature", f"signature length {len(sig_bytes)} ≠ 64")

    canonical = _canonical_bytes_for_signing(receipt)
    try:
        pubkey.verify(sig_bytes, canonical)
    except InvalidSignature:
        return VerificationResult(False, "signature", "Ed25519 verification failed")
    return VerificationResult.accepted()


def validate_schema(receipt: dict[str, Any]) -> VerificationResult:
    """Run the receipt against the JSON Schema. Returns failure on first error."""
    errors = list(_VALIDATOR.iter_errors(receipt))
    if errors:
        first = errors[0]
        detail = f"{first.message} at {list(first.absolute_path)}"
        return VerificationResult(False, "schema", detail)
    return VerificationResult.accepted()


def _check_window_args(now: datetime, max_skew_seconds: int) -> None:
    """A naive ``now`` or a negative/non-int window is a caller bug: raise rather
    than return a verdict that means nothing."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    if (
        isinstance(max_skew_seconds, bool)
        or not isinstance(max_skew_seconds, int)
        or max_skew_seconds < 0
    ):
        raise ValueError(f"max_skew_seconds must be a non-negative int, got {max_skew_seconds!r}")


def verify_freshness(
    receipt: dict[str, Any],
    *,
    now: datetime,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> VerificationResult:
    """Spec §3.3 / §6.3 step 6: ``issued_at`` within ``max_skew_seconds`` of the
    verifier's reference instant ``now`` (inclusive; rejects stale and
    forward-dated receipts). ``now`` is the current time for live acceptance, or
    an independently evidenced instant for after-the-fact checks."""
    _check_window_args(now, max_skew_seconds)
    raw = receipt.get("issued_at")
    try:
        issued = datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None
    except ValueError:
        issued = None
    if issued is None or issued.utcoffset() is None:
        return VerificationResult(
            False, "freshness", "issued_at is not an RFC 3339 timestamp with a UTC offset"
        )
    skew = (issued - now).total_seconds()
    if abs(skew) > max_skew_seconds:
        direction = "forward-dated" if skew > 0 else "stale"
        return VerificationResult(
            False,
            "freshness",
            f"issued_at is {abs(skew):.0f}s from the reference instant "
            f"({direction}; window ±{max_skew_seconds}s)",
        )
    return VerificationResult.accepted()


def verify_reversal(
    receipt: dict[str, Any], originals: Mapping[str, dict[str, Any]]
) -> VerificationResult:
    """Spec §4.2: a reversal's issuer must be the original receipt's issuer.

    ``originals`` holds the receipts the verifier has, keyed by ``receipt_id``. A
    receipt that is not a reversal passes, and so does a reversal whose original
    is not held (the rule cannot be evaluated). A held original must sit under
    its own ``receipt_id`` and carry a valid signature before its ``issuer_did``
    is compared. A receipt that names itself as the one it reverses fails.
    """
    action = receipt.get("action")
    if not isinstance(action, dict) or "reversal_of_receipt_id" not in action:
        return VerificationResult.accepted()
    target = action["reversal_of_receipt_id"]
    if not isinstance(target, str) or not target:
        return VerificationResult(
            False, "reversal", "reversal_of_receipt_id is not a non-empty string"
        )
    if target == receipt.get("receipt_id"):
        return VerificationResult(
            False, "reversal", "receipt names itself as the receipt it reverses"
        )
    if target not in originals:
        return VerificationResult.accepted()
    original = originals[target]
    if not isinstance(original, dict):
        return VerificationResult(False, "reversal", f"original {target} is not a receipt object")
    if original.get("receipt_id") != target:
        return VerificationResult(
            False, "reversal", f"originals index key {target} does not match its receipt_id"
        )
    authentic = verify_signature(original)
    if not authentic.ok:
        return VerificationResult(
            False, "reversal", f"original {target} signature: {authentic.detail}"
        )
    if original.get("issuer_did") != receipt.get("issuer_did"):
        return VerificationResult(
            False, "reversal", f"reversal issuer is not the issuer of original {target}"
        )
    return VerificationResult.accepted()


def verify_receipt(
    receipt: dict[str, Any],
    *,
    mode: str = "strict",
    prior_receipts: dict[str, dict[str, Any]] | None = None,
    originals: Mapping[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
    max_skew_seconds: int | None = None,
) -> VerificationResult:
    """Top-level verification pipeline.

    Order:
      1. Schema validation
      2. Signature verification
      3. Freshness (only when ``now`` is supplied): ``issued_at`` within
         ``max_skew_seconds`` (default 300) of ``now``. Vectors that carry a
         ``verifier_now`` are run with it. Without ``now`` the receipt is being
         verified after the fact and no window applies (spec §3.3).
      4. Reversal issuer (only when ``originals`` is supplied, keyed by
         ``receipt_id``): see :func:`verify_reversal`.
      5. Hash chain verification (if previous_receipt_hash present AND
         a matching prior receipt is supplied via ``prior_receipts`` keyed
         by hash)

    ``prior_receipts`` is an optional mapping from previous_receipt_hash
    value to the prior canonicalized receipt. If the receipt declares a
    previous_receipt_hash but no matching prior is provided, this is
    treated as ``hash_chain`` failure in ``strict`` mode and as
    ``accepted`` in ``tolerant`` mode (the verifier acknowledges the
    chain claim cannot be evaluated without the prior).

    ``mode`` must be ``"strict"`` or ``"tolerant"``; anything else raises
    ``ValueError`` instead of silently behaving as tolerant. A naive ``now``, a
    negative or non-int ``max_skew_seconds``, or ``max_skew_seconds`` without
    ``now`` also raise.
    """
    if mode not in VERIFIER_MODES:
        raise ValueError(f"unknown verifier mode {mode!r}; expected one of {VERIFIER_MODES}")
    window = DEFAULT_MAX_SKEW_SECONDS if max_skew_seconds is None else max_skew_seconds
    if now is None:
        if max_skew_seconds is not None:
            raise ValueError("max_skew_seconds has no effect without now")
    else:
        _check_window_args(now, window)
    schema_res = validate_schema(receipt)
    if not schema_res.ok:
        return schema_res

    sig_res = verify_signature(receipt)
    if not sig_res.ok:
        return sig_res

    if now is not None:
        fresh_res = verify_freshness(receipt, now=now, max_skew_seconds=window)
        if not fresh_res.ok:
            return fresh_res

    if originals is not None:
        reversal_res = verify_reversal(receipt, originals)
        if not reversal_res.ok:
            return reversal_res

    prev_hash = receipt.get("previous_receipt_hash")
    if prev_hash:
        if prior_receipts is None or prev_hash not in prior_receipts:
            if mode == "strict":
                return VerificationResult(
                    False,
                    "hash_chain",
                    f"previous_receipt_hash {prev_hash} not satisfied by any provided prior",
                )
            return VerificationResult(
                True,
                "accepted",
                "chain claim recorded; prior not provided (tolerant mode)",
            )
        prior = prior_receipts[prev_hash]
        recomputed = compute_chain_link(prior)
        if recomputed != prev_hash:
            return VerificationResult(
                False,
                "hash_chain",
                f"declared {prev_hash} does not match recomputed {recomputed}",
            )

    return VerificationResult.accepted()


def compute_chain_link(prior_receipt: dict[str, Any]) -> str:
    """sha256: hash of the canonical receipt INCLUDING its signature and
    EXCLUDING the detached ``evidence.witness_signatures`` (spec §6.4).

    This is the value the next receipt's ``previous_receipt_hash`` MUST
    equal to form a valid chain. Because witnesses are detached, a co-signature
    appended to the prior after the successor was issued does not break the link.
    """
    canonical = jcs.canonicalize(_detach_witnesses(prior_receipt))
    digest = hashlib.sha256(canonical).hexdigest()
    return f"sha256:{digest}"


# ── module exports ─────────────────────────────────────────────────


__all__ = [
    "DEFAULT_MAX_SKEW_SECONDS",
    "VERIFIER_MODES",
    "VerificationResult",
    "compute_chain_link",
    "validate_schema",
    "verify_freshness",
    "verify_receipt",
    "verify_reversal",
    "verify_signature",
]
