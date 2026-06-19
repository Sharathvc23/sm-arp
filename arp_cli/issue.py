"""Receipt-issuing helpers shared by `arp issue`, `arp grant`, `arp revoke`.

Mirrors conformance/arp/_vector_gen.py's primitives (keypair, did_key, sign)
so the CLI's write-side stays consistent with the upstream vector generator
without depending on a "_private" module.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import base58
import jcs
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


# ── seeds and identities ───────────────────────────────────────────


def random_seed() -> bytes:
    """Cryptographically random 32-byte seed for a fresh Ed25519 keypair."""
    return secrets.token_bytes(32)


def parse_seed(spec: str) -> bytes:
    """Parse a --issuer-key spec into 32 raw bytes.

    Accepted forms:
      32-byte ASCII string:   "nanda-demo-human-principal-32by!"
      base64:<b64-32-bytes>:  "base64:1qS9..."
      @path/to/file:          read file; strip; treat content as base64 or raw
    """
    if spec.startswith("@"):
        path = Path(spec[1:])
        if not path.is_file():
            raise ValueError(f"seed file not found: {path}")
        content = path.read_text().strip()
        # Try base64 first; fall back to raw bytes if content is exactly 32 bytes.
        try:
            decoded = base64.b64decode(content, validate=True)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        raw = content.encode("utf-8")
        if len(raw) == 32:
            return raw
        raise ValueError(
            f"seed file must contain 32 raw bytes or base64-encoded 32 bytes; got {len(raw)} bytes / {len(content)} chars"
        )

    if spec.startswith("base64:"):
        decoded = base64.b64decode(spec[len("base64:") :], validate=True)
        if len(decoded) != 32:
            raise ValueError(f"base64 seed decodes to {len(decoded)} bytes, expected 32")
        return decoded

    raw = spec.encode("utf-8")
    if len(raw) != 32:
        raise ValueError(
            f"seed must be exactly 32 bytes; got {len(raw)} "
            f"(quote the value, use base64:..., or @file form)"
        )
    return raw


def keypair_from_seed(seed: bytes) -> tuple[Ed25519PrivateKey, bytes]:
    if len(seed) != 32:
        raise ValueError(f"seed must be 32 bytes; got {len(seed)}")
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_bytes = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sk, pk_bytes


def did_key_from_pubkey(pk_bytes: bytes) -> str:
    """W3C did:key — multibase z-base58btc over multicodec 0xed01 ‖ pubkey32."""
    if len(pk_bytes) != 32:
        raise ValueError(f"Ed25519 pubkey must be 32 bytes; got {len(pk_bytes)}")
    return "did:key:z" + base58.b58encode(b"\xed\x01" + pk_bytes).decode("ascii")


def did_key_for_seed(seed: bytes) -> str:
    _, pk = keypair_from_seed(seed)
    return did_key_from_pubkey(pk)


# Well-known demo seeds (committed to the repo); warn if encountered in
# `arp issue` so users don't accidentally sign production traffic with them.
DEMO_SEEDS_HEX: set[str] = {
    bytes(b"nanda-demo-human-principal-32by!").hex(),
    bytes(b"nanda-demo-agent-a-seed-32-byte!").hex(),
    bytes(b"nanda-demo-agent-b-seed-32-byte!").hex(),
    bytes(b"arp-vector-issuer-seed-32bytes!!").hex(),
    bytes(b"arp-vector-principal-seed-32by!!").hex(),
    bytes(b"arp-vector-witness-seed-32bytes!").hex(),
    bytes(b"arp-vector-counterparty-seed32b!").hex(),
}


def seed_is_well_known(seed: bytes) -> bool:
    return seed.hex() in DEMO_SEEDS_HEX


# ── receipts ───────────────────────────────────────────────────────


_UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_RFC3339_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def new_receipt_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    """RFC 3339, second-precision, UTC, Z suffix — matches the issued_at pattern."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_action(
    *,
    category: str,
    human_summary: str,
    outcome: str = "completed",
    counterparty_did: str | None = None,
    counterparty_label: str | None = None,
    amount_cents: int | None = None,
    currency: str = "USD",
    granted_by_receipt_id: str | None = None,
    reversal_of_receipt_id: str | None = None,
    machine_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the action object with only the populated optional fields."""
    action: dict[str, Any] = {
        "category": category,
        "human_summary": human_summary,
        "outcome": outcome,
    }
    if counterparty_did:
        action["counterparty_did"] = counterparty_did
    if counterparty_label:
        action["counterparty_label"] = counterparty_label
    if amount_cents is not None:
        action["amount"] = {"currency": currency, "cents": amount_cents}
    if granted_by_receipt_id:
        action["granted_by_receipt_id"] = granted_by_receipt_id
    if reversal_of_receipt_id:
        action["reversal_of_receipt_id"] = reversal_of_receipt_id
    if machine_payload:
        action["machine_payload"] = machine_payload
    return action


def build_receipt(
    *,
    issuer_did: str,
    principal_did: str,
    action: dict[str, Any],
    receipt_id: str | None = None,
    issued_at: str | None = None,
    authority_chain: list[str] | None = None,
) -> dict[str, Any]:
    rid = receipt_id or new_receipt_id()
    iso = issued_at or now_iso()
    if not _UUID_V4_RE.match(rid):
        raise ValueError(f"receipt_id {rid!r} is not a canonical UUIDv4")
    if not _RFC3339_UTC_RE.match(iso):
        raise ValueError(
            f"issued_at {iso!r} must be RFC 3339 UTC at second precision (YYYY-MM-DDTHH:MM:SSZ)"
        )
    r: dict[str, Any] = {
        "version": "arp/0.1",
        "receipt_id": rid,
        "issuer_did": issuer_did,
        "principal_did": principal_did,
        "issued_at": iso,
        "action": action,
    }
    if authority_chain:
        r["authority_chain"] = authority_chain
    return r


def sign(seed: bytes, receipt: dict[str, Any]) -> dict[str, Any]:
    """JCS-canonicalize the body sans-signature, Ed25519-sign, attach b64 sig."""
    sk, _ = keypair_from_seed(seed)
    body = {k: v for k, v in receipt.items() if k != "signature"}
    canonical = jcs.canonicalize(body)
    sig_bytes = sk.sign(canonical)
    assert len(sig_bytes) == 64
    receipt["signature"] = base64.b64encode(sig_bytes).decode("ascii")
    return receipt


def parse_payload(json_str: str | None) -> dict[str, Any] | None:
    """Parse a --payload='...' JSON string. Returns None if input is None/empty."""
    if not json_str:
        return None
    try:
        out = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"--payload is not valid JSON: {e}")
    if not isinstance(out, dict):
        raise ValueError("--payload must be a JSON object")
    return out
