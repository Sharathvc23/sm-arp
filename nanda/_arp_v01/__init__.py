"""ARP v0.1 conformance harness — VENDORED SNAPSHOT.

This file is a snapshot of ``conformance/arp/__init__.py`` from
sm-arp v0.1.0 (github.com/Sharathvc23/sm-arp), vendored so the NANDA
prototype in this directory runs standalone — no `pip install sm-arp`
required, only the pip-installable libraries listed in requirements.txt.

The only change from upstream is ``SCHEMA_DIR`` below, which points at
the JSON Schemas vendored alongside this file in ``./schemas/`` instead
of sm-arp's top-level ``schema/arp/0.1/`` tree.

For the canonical implementation (which may evolve), refer to:
  https://github.com/Sharathvc23/sm-arp/blob/main/conformance/arp/__init__.py

────────────────────────────────────────────────────────────────────────
Original upstream docstring:

Public entry points:

    verify_receipt(receipt: dict, *, mode: str = "strict") -> VerificationResult

Loads JSON Schemas with $ref resolution, validates the receipt envelope,
verifies the Ed25519 signature against canonicalized bytes, and (when
``previous_receipt_hash`` is present) the caller can verify the hash chain
via ``compute_chain_link(prior_receipt)``.

The harness is intentionally framework-agnostic: nothing in this package
imports any runtime-specific modules. Any ARP implementation can
run these vectors against its own emit pipeline by importing
``verify_receipt`` from here.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jcs
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


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
    stage: str  # one of: schema, signature, hash_chain, accepted
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


def _canonical_bytes_for_signing(receipt: dict[str, Any]) -> bytes:
    """JCS-canonical bytes of the receipt with the signature field removed."""
    body = {k: v for k, v in receipt.items() if k != "signature"}
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


def verify_receipt(
    receipt: dict[str, Any],
    *,
    mode: str = "strict",
    prior_receipts: dict[str, dict[str, Any]] | None = None,
) -> VerificationResult:
    """Top-level verification pipeline.

    Order:
      1. Schema validation
      2. Signature verification
      3. Hash chain verification (if previous_receipt_hash present AND
         a matching prior receipt is supplied via ``prior_receipts`` keyed
         by hash)

    ``prior_receipts`` is an optional mapping from previous_receipt_hash
    value to the prior canonicalized receipt. If the receipt declares a
    previous_receipt_hash but no matching prior is provided, this is
    treated as ``hash_chain`` failure in ``strict`` mode and as
    ``accepted`` in ``tolerant`` mode (the verifier acknowledges the
    chain claim cannot be evaluated without the prior).
    """
    schema_res = validate_schema(receipt)
    if not schema_res.ok:
        return schema_res

    sig_res = verify_signature(receipt)
    if not sig_res.ok:
        return sig_res

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
    """sha256: hash of the full canonical receipt INCLUDING signature.

    This is the value the next receipt's ``previous_receipt_hash`` MUST
    equal to form a valid chain.
    """
    canonical = jcs.canonicalize(prior_receipt)
    digest = hashlib.sha256(canonical).hexdigest()
    return f"sha256:{digest}"


# ── module exports ─────────────────────────────────────────────────


__all__ = [
    "VerificationResult",
    "compute_chain_link",
    "validate_schema",
    "verify_receipt",
    "verify_signature",
]
