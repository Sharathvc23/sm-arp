"""Signed conformance badge — generation, canonical encoding, and verification.

A conformance badge is the wrapped envelope a runtime ships at
``.nanda/conformance.json`` to prove it passes the suite at a specific
commit. The badge is signed by the runtime's Ed25519 key; the verifier
canonically re-encodes the payload and confirms the signature against
the ``signed_by`` did:key.

Envelope shape::

    {
      "payload": {
        "schema_version": 1,
        "runtime": "spec-reference",
        "protocol_versions": ["0.2", "0.3"],
        "suite_digest": "sha256:<hex>",
        "completed_at": "<iso8601>",
        "exit_status": 0,
        "passed": 47, "failed": 0, "skipped": 1,
        "xfailed": 0, "xpassed": 0
      },
      "signed_by": "did:key:z6Mk...",
      "signed_at": "<iso8601>",
      "signature": "<base64>"
    }

The signature is over the UTF-8 bytes of ``canonical_json(payload)``.
For payloads containing only ASCII strings, ints, bools, null, and
nested dicts/lists with the same constraint, the encoding is byte-
identical to RFC 8785 JCS. Non-ASCII or floating-point payloads will
require proper JCS — flagged as future work for spec/arp/0.X.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import base58
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ED25519_MULTICODEC_PREFIX = b"\xed\x01"
DEFAULT_VECTORS_ROOT = Path(__file__).resolve().parent.parent / "vectors"


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 encoding for signing — sorted keys, no whitespace."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def derive_did_key(pubkey32: bytes) -> str:
    if len(pubkey32) != 32:
        raise ValueError(f"Ed25519 public key must be 32 bytes, got {len(pubkey32)}")
    prefixed = ED25519_MULTICODEC_PREFIX + pubkey32
    encoded = base58.b58encode(prefixed).decode()
    return f"did:key:z{encoded}"


def parse_did_key(did_key: str) -> bytes:
    """Inverse of derive_did_key — returns the 32-byte public key."""
    if not did_key.startswith("did:key:z"):
        raise ValueError(f"not a did:key: {did_key!r}")
    multibase = did_key[len("did:key:z") :]
    decoded = base58.b58decode(multibase)
    if not decoded.startswith(ED25519_MULTICODEC_PREFIX):
        raise ValueError(f"did:key does not encode an Ed25519 key: {did_key!r}")
    pubkey = decoded[len(ED25519_MULTICODEC_PREFIX) :]
    if len(pubkey) != 32:
        raise ValueError(f"decoded key has wrong length: {len(pubkey)}")
    return pubkey


def compute_suite_digest(vectors_root: Path = DEFAULT_VECTORS_ROOT) -> str:
    """sha256 over every JSON vector file under vectors_root.

    Pins a badge to a specific commit of the conformance suite. Any change
    to any vector file changes the digest, invalidating prior badges.
    """
    hasher = hashlib.sha256()
    files = sorted(p for p in vectors_root.rglob("*.json"))
    for path in files:
        rel = path.relative_to(vectors_root).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(path.read_bytes())
        hasher.update(b"\x00")
    return f"sha256:{hasher.hexdigest()}"


def load_signing_key(path: Path) -> bytes:
    """Read an Ed25519 private key — 64 hex characters (preferred) or 32 raw bytes.

    Hex is the canonical format. Raw is best-effort: a legitimate 32-byte raw
    key that happens to end in 0x0a or 0x20 cannot be distinguished from a
    33-byte hex file with trailing whitespace, so this routine never strips
    raw bytes — the file must be exactly 32 bytes long for the raw path.
    """
    raw = path.read_bytes()
    # Hex path: file is a printable ASCII hex string, possibly with trailing
    # whitespace from an editor. Strip and require exactly 64 hex chars.
    try:
        stripped = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        stripped = None
    if (
        stripped is not None
        and len(stripped) == 64
        and all(c in "0123456789abcdefABCDEF" for c in stripped)
    ):
        return bytes.fromhex(stripped)
    # Raw path: file must be exactly 32 bytes, no stripping.
    if len(raw) == 32:
        return raw
    raise ValueError(
        f"signing key file {path} must be 64 hex characters (preferred) "
        f"or exactly 32 raw bytes, got {len(raw)} bytes"
    )


def sign_envelope(
    payload: dict[str, Any],
    private_key32: bytes,
    signed_at: str,
) -> dict[str, Any]:
    """Wrap payload in a signed envelope ready for JSON serialization."""
    if len(private_key32) != 32:
        raise ValueError(f"Ed25519 seed must be 32 bytes, got {len(private_key32)}")
    priv = Ed25519PrivateKey.from_private_bytes(private_key32)
    pub_bytes = priv.public_key().public_bytes_raw()
    did_key = derive_did_key(pub_bytes)
    canonical = canonical_json(payload)
    signature = priv.sign(canonical)
    return {
        "payload": payload,
        "signed_by": did_key,
        "signed_at": signed_at,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


class VerificationError(Exception):
    pass


def verify_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Verify a signed envelope. Returns the payload on success; raises otherwise."""
    for field in ("payload", "signed_by", "signed_at", "signature"):
        if field not in envelope:
            raise VerificationError(f"envelope missing required field: {field}")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise VerificationError("payload must be an object")
    try:
        pubkey = parse_did_key(envelope["signed_by"])
    except ValueError as exc:
        raise VerificationError(f"invalid signed_by: {exc}") from exc
    try:
        sig = base64.b64decode(envelope["signature"], validate=True)
    except Exception as exc:
        raise VerificationError(f"signature is not valid base64: {exc}") from exc
    canonical = canonical_json(payload)
    pub = Ed25519PublicKey.from_public_bytes(pubkey)
    try:
        pub.verify(sig, canonical)
    except InvalidSignature as exc:
        raise VerificationError("signature verification failed") from exc
    return payload
