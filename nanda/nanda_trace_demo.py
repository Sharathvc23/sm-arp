#!/usr/bin/env python3
"""NANDA Causal Delegation Trace demo — ARP v0.1.

Produces three Ed25519-signed Agency Receipts that form a directed graph of
delegated authority, then validates the output against the JSON Schemas and
Ed25519 verifier vendored at ``./_arp_v01/`` (a snapshot of sm-arp v0.1.0)
before exiting.

This script is intentionally self-contained: clone or copy this directory
to any location, install requirements.txt, and run. No `pip install sm-arp`
required.

    Receipt 1  (Human Principal grants Agent A          authority_granted)
        ↑
        │  action.granted_by_receipt_id
        │
    Receipt 2  (Agent A sub-delegates to Agent B        authority_granted)
        ↑
        │  action.granted_by_receipt_id
        │
    Receipt 3  (Agent B shares data with NANDA Registry data_shared)

The trace is deterministic: seeds, UUIDs, and timestamps are all fixed so
every run produces a byte-identical nanda_interaction_trace.json that any
consumer can diff, hash, and pin against.

Run::

    pip install -r requirements.txt
    python nanda_trace_demo.py

Exits 0 on success; nonzero on any schema, signature, or authority-chain
violation. The JSON output is written next to this script.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

# Make the vendored _arp_v01 package importable whether this script is run
# from inside its own directory or from a parent. We add the script's own
# directory to sys.path so `from _arp_v01 import ...` works either way.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import base58
import jcs
from _arp_v01 import verify_receipt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# ── deterministic demo identities ───────────────────────────────────
#
# DEMO ONLY. These seeds are committed to the repo so the trace is
# reproducible for inspection. Do NOT reuse them outside this demo —
# anyone with this file can sign as the "Human Principal", "Agent A",
# or "Agent B" identities below.

HUMAN_SEED = b"nanda-demo-human-principal-32by!"
AGENT_A_SEED = b"nanda-demo-agent-a-seed-32-byte!"
AGENT_B_SEED = b"nanda-demo-agent-b-seed-32-byte!"

assert len(HUMAN_SEED) == 32
assert len(AGENT_A_SEED) == 32
assert len(AGENT_B_SEED) == 32


# ── primitives (mirror conformance/arp/_vector_gen.py for self-containment) ──


def keypair(seed: bytes) -> tuple[Ed25519PrivateKey, bytes]:
    """Ed25519 keypair from a 32-byte seed. Returns (private_key, raw_pubkey32)."""
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_bytes = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sk, pk_bytes


def did_key_from_pubkey(pk_bytes: bytes) -> str:
    """W3C did:key — multibase z-base58btc over multicodec 0xed01 ‖ pubkey32."""
    prefixed = b"\xed\x01" + pk_bytes
    return "did:key:z" + base58.b58encode(prefixed).decode("ascii")


def sign_receipt(sk: Ed25519PrivateKey, receipt: dict) -> dict:
    """JCS-canonicalize the receipt sans-signature, Ed25519-sign, attach b64 sig."""
    body = {k: v for k, v in receipt.items() if k != "signature"}
    canonical = jcs.canonicalize(body)
    sig_bytes = sk.sign(canonical)
    assert len(sig_bytes) == 64, f"Ed25519 signature length {len(sig_bytes)} ≠ 64"
    receipt["signature"] = base64.b64encode(sig_bytes).decode("ascii")
    return receipt


# ── identity setup ──────────────────────────────────────────────────

HUMAN_SK, HUMAN_PK = keypair(HUMAN_SEED)
AGENT_A_SK, AGENT_A_PK = keypair(AGENT_A_SEED)
AGENT_B_SK, AGENT_B_PK = keypair(AGENT_B_SEED)

HUMAN_DID = did_key_from_pubkey(HUMAN_PK)
AGENT_A_DID = did_key_from_pubkey(AGENT_A_PK)
AGENT_B_DID = did_key_from_pubkey(AGENT_B_PK)


# ── fixed identifiers for reproducibility ───────────────────────────
#
# UUIDv4 canonical form: 8-4-4-4-12 hex with version nibble 4 and variant
# nibble in [89ab]. These pass the schema pattern in common.schema.json.

RECEIPT_1_ID = "10000001-0001-4001-8001-100000000001"
RECEIPT_2_ID = "20000002-0002-4002-8002-200000000002"
RECEIPT_3_ID = "30000003-0003-4003-8003-300000000003"

# Issued timestamps: RFC 3339, second precision, UTC, Z suffix.
ISSUED_AT_1 = "2026-06-03T12:00:00Z"
ISSUED_AT_2 = "2026-06-03T12:15:00Z"
ISSUED_AT_3 = "2026-06-03T12:30:00Z"

# Both grants expire end of year — comfortably after every issued_at above.
GRANT_EXPIRES_AT = "2026-12-31T23:59:59Z"


# ── receipt builders ────────────────────────────────────────────────


def build_receipt_1_grant() -> dict:
    """Human Principal grants Agent A scope = [data_shared, message_sent, authority_granted].

    The third scope element is the load-bearing one for sub-delegation: per
    spec §4.5 step 5, Receipt 2's action.category ('authority_granted') must
    appear in this grant's machine_payload.granted_scope for the strict-mode
    verifier to accept the chain. We make the right to sub-delegate explicit
    rather than relying on the wildcard '*' shorthand.
    """
    r: dict = {
        "version": "arp/0.1",
        "receipt_id": RECEIPT_1_ID,
        "issuer_did": HUMAN_DID,
        "principal_did": HUMAN_DID,
        "issued_at": ISSUED_AT_1,
        "action": {
            "category": "authority_granted",
            "human_summary": (
                "Granted Agent A authority to share data and send messages on my "
                "behalf, including the right to sub-delegate."
            ),
            "outcome": "completed",
            "machine_payload": {
                "granted_scope": ["data_shared", "message_sent", "authority_granted"],
                "granted_to_did": AGENT_A_DID,
                "grant_expires_at": GRANT_EXPIRES_AT,
            },
        },
    }
    return sign_receipt(HUMAN_SK, r)


def build_receipt_2_delegation() -> dict:
    """Agent A sub-delegates the data-sharing slice of its authority to Agent B.

    principal_did stays the Human throughout: per spec §4.5 step 2, the
    referenced receipt's principal_did must equal this receipt's
    principal_did. The issuer changes (Agent A signs this one), but the
    principal of record is still the Human who rooted the chain.

    granted_scope is narrower than Receipt 1's — only data_shared. Agent B
    receives no authority to send messages or sub-delegate further.
    """
    r: dict = {
        "version": "arp/0.1",
        "receipt_id": RECEIPT_2_ID,
        "issuer_did": AGENT_A_DID,
        "principal_did": HUMAN_DID,
        "issued_at": ISSUED_AT_2,
        "action": {
            "category": "authority_granted",
            "human_summary": (
                "Sub-delegated data-sharing authority to Agent B under the Human Principal's grant."
            ),
            "outcome": "completed",
            "granted_by_receipt_id": RECEIPT_1_ID,
            "machine_payload": {
                "granted_scope": ["data_shared"],
                "granted_to_did": AGENT_B_DID,
                "grant_expires_at": GRANT_EXPIRES_AT,
            },
        },
    }
    return sign_receipt(AGENT_A_SK, r)


def build_receipt_3_action() -> dict:
    """Agent B executes data_shared with the NANDA Registry, under Receipt 2.

    Two edges back to the chain root:

      - action.granted_by_receipt_id → Receipt 2's UUID (immediate parent)
      - authority_chain → [HUMAN_DID] (top-level root principal)

    Reverse traversal:
      Receipt 3.action.granted_by_receipt_id == Receipt 2.receipt_id
      Receipt 2.action.granted_by_receipt_id == Receipt 1.receipt_id
      Receipt 1 has no granted_by_receipt_id  → root of the chain
    """
    r: dict = {
        "version": "arp/0.1",
        "receipt_id": RECEIPT_3_ID,
        "issuer_did": AGENT_B_DID,
        "principal_did": HUMAN_DID,
        "issued_at": ISSUED_AT_3,
        "action": {
            "category": "data_shared",
            "human_summary": (
                "Shared compliance summary with the NANDA Registry under delegated "
                "authority from the Human Principal."
            ),
            "outcome": "completed",
            "counterparty_label": "NANDA Registry",
            "granted_by_receipt_id": RECEIPT_2_ID,
            "machine_payload": {
                "fields_shared": ["compliance_summary"],
                "purpose": "registry_attestation",
            },
        },
        "authority_chain": [HUMAN_DID],
    }
    return sign_receipt(AGENT_B_SK, r)


# ── authority-chain walk (spec §4.5 strict-mode checks) ─────────────


def _walk_edge(child: dict, parent: dict) -> None:
    """Enforce spec §4.5 steps 1-5 for one edge (child → parent grant).

    Step 6 (revocation check) is N/A in this demo — no authority_revoked
    receipts exist in the trace.
    """
    cid = child["receipt_id"]
    pid = parent["receipt_id"]

    # 1. The edge is resolvable.
    assert child["action"]["granted_by_receipt_id"] == pid, (
        f"{cid}: granted_by_receipt_id does not point at {pid}"
    )

    # 2. Same principal at both ends.
    assert child["principal_did"] == parent["principal_did"], (
        f"{cid}: principal_did differs from referenced grant {pid}"
    )

    # 3. Referenced receipt is a grant.
    assert parent["action"]["category"] == "authority_granted", (
        f"{cid}: referenced receipt {pid} is not authority_granted"
    )

    # 4. Grant has not expired at the time of the child action.
    expires = parent["action"]["machine_payload"]["grant_expires_at"]
    assert expires > child["issued_at"], (
        f"{cid}: referenced grant {pid} expired ({expires} ≤ {child['issued_at']})"
    )

    # 5. The child's action category is within the parent's granted scope.
    scope = parent["action"]["machine_payload"]["granted_scope"]
    cat = child["action"]["category"]
    assert cat in scope or "*" in scope, (
        f"{cid}: category {cat!r} not in parent {pid}'s granted_scope {scope}"
    )


def walk_authority_chain(trace: list[dict]) -> None:
    """Walk Receipt 3 → Receipt 2 → Receipt 1, asserting every §4.5 edge."""
    by_id = {r["receipt_id"]: r for r in trace}
    receipt_3, receipt_2, receipt_1 = (
        by_id[RECEIPT_3_ID],
        by_id[RECEIPT_2_ID],
        by_id[RECEIPT_1_ID],
    )

    _walk_edge(receipt_3, receipt_2)
    _walk_edge(receipt_2, receipt_1)

    # Receipt 1 is the genesis grant: it MUST NOT carry granted_by_receipt_id.
    assert "granted_by_receipt_id" not in receipt_1["action"], (
        f"{RECEIPT_1_ID}: genesis grant must not reference a prior receipt"
    )

    # Top-level authority_chain on the action receipt names the root principal.
    assert receipt_3["authority_chain"] == [receipt_1["issuer_did"]], (
        f"{RECEIPT_3_ID}: authority_chain does not name the genesis issuer"
    )


# ── main ────────────────────────────────────────────────────────────


def main() -> int:
    out_path = Path(__file__).resolve().parent / "nanda_interaction_trace.json"

    print("Building NANDA Causal Delegation Trace (ARP v0.1)")
    print(f"  Human Principal: {HUMAN_DID}")
    print(f"  Agent A:         {AGENT_A_DID}")
    print(f"  Agent B:         {AGENT_B_DID}")
    print()

    trace = [
        build_receipt_1_grant(),
        build_receipt_2_delegation(),
        build_receipt_3_action(),
    ]

    out_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out_path.relative_to(Path.cwd())}")
    print()

    print("Self-validation (sm-arp conformance verifier + spec §4.5 walk)")
    failures: list[str] = []

    for idx, receipt in enumerate(trace, start=1):
        result = verify_receipt(receipt, mode="strict")
        status = "OK" if result.ok else f"FAIL ({result.stage}: {result.detail})"
        print(f"  Receipt {idx} [{receipt['receipt_id']}] → {status}")
        if not result.ok:
            failures.append(f"Receipt {idx}: {result.stage}: {result.detail}")

    if failures:
        print()
        print("Verification failures:")
        for f in failures:
            print(f"  - {f}")
        return 1

    try:
        walk_authority_chain(trace)
    except AssertionError as e:
        print(f"  Authority chain walk → FAIL ({e})")
        return 1
    print("  Authority chain walk → OK (Receipt 3 → Receipt 2 → Receipt 1)")

    print()
    print("Trace verified. Output is mathematically sound under ARP v0.1 strict mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
