"""Conformance for ``sm_arp.vrp`` counterparty corroboration (VRP 0.3 §A).

Pins ``cosign_receipt`` + ``is_corroborated`` so every consumer recomputes
identical corroboration, and asserts **byte-for-byte** equality with the canonical
NANDA reference via an embedded golden vector. A corroboration that diverged by a
single byte would give an agent a different reputation on different runtimes —
exactly the drift these primitives exist to prevent.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sm_arp.identity import did_from_sk, gen_key
from sm_arp.vrp import cosign_receipt, did_key_from_pubkey, is_corroborated, pubkey_from_did_key

# Golden reference output for the fixed seed 0x00..0x1f and the receipt built by
# ``_receipt`` below. ``sm_arp.cosign_receipt`` MUST reproduce it byte-for-byte —
# this is the cross-implementation equivalence pin (a co-signature that diverges by
# one byte would give an agent a different reputation on a different runtime).
_GOLDEN_SEED = bytes(range(32))
_GOLDEN_B_DID = "did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd"
_GOLDEN_ENTRY = {
    "witness_did": "did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd",
    "signature": "aY8FOs0ah3t2BFRv9a6cGHUQ4Gd6CR3AxxIdQdM4Ca2q8H8QjddPrk9Uzfz4UvpBGG5LMb5Hc71LpZCyAEG+Cw==",
}


def _receipt(issuer_did: str, counterparty_did: str) -> dict:
    return {
        "version": "arp/0.1",
        "receipt_id": "fixed",
        "issuer_did": issuer_did,
        "issued_at": "2026-01-01T00:00:00Z",
        "action": {
            "category": "message_sent",
            "human_summary": "x",
            "outcome": "completed",
            "counterparty_did": counterparty_did,
        },
    }


def test_golden_matches_canonical_byte_for_byte() -> None:
    assert did_from_sk(_GOLDEN_SEED) == _GOLDEN_B_DID
    r = _receipt("did:key:zISSUER", _GOLDEN_B_DID)
    entry = cosign_receipt(r, signing_key_bytes=_GOLDEN_SEED, witness_did=_GOLDEN_B_DID)
    assert entry == _GOLDEN_ENTRY


def test_cosign_then_corroborated_roundtrip() -> None:
    a, b = gen_key(), gen_key()
    b_did = did_from_sk(b)
    r = _receipt(did_from_sk(a), b_did)
    entry = cosign_receipt(r, signing_key_bytes=b)
    assert entry["witness_did"] == b_did
    r["evidence"] = {"witness_signatures": [entry]}
    assert is_corroborated(r) is True


def test_witness_did_defaults_to_signer() -> None:
    b = gen_key()
    r = _receipt("did:key:zA", did_from_sk(b))
    assert cosign_receipt(r, signing_key_bytes=b)["witness_did"] == did_from_sk(b)


def test_no_witness_is_not_corroborated() -> None:
    a, b = gen_key(), gen_key()
    assert is_corroborated(_receipt(did_from_sk(a), did_from_sk(b))) is False


def test_self_counterparty_never_corroborates() -> None:
    # issuer == counterparty: even a valid self-signature does not corroborate (§A.1).
    a = gen_key()
    a_did = did_from_sk(a)
    r = _receipt(a_did, a_did)
    entry = cosign_receipt(r, signing_key_bytes=a)
    r["evidence"] = {"witness_signatures": [entry]}
    assert is_corroborated(r) is False


def test_wrong_signer_not_corroborated() -> None:
    # C signs the right payload but the entry claims B as the witness.
    a, b, c = gen_key(), gen_key(), gen_key()
    b_did = did_from_sk(b)
    r = _receipt(did_from_sk(a), b_did)
    entry = cosign_receipt(r, signing_key_bytes=c, witness_did=b_did)
    r["evidence"] = {"witness_signatures": [entry]}
    assert is_corroborated(r) is False


def test_third_party_witness_does_not_corroborate() -> None:
    # A co-signer who is not the named counterparty does not corroborate (§2).
    a, b, c = gen_key(), gen_key(), gen_key()
    r = _receipt(did_from_sk(a), did_from_sk(b))
    r["evidence"] = {"witness_signatures": [cosign_receipt(r, signing_key_bytes=c)]}
    assert is_corroborated(r) is False


def test_garbage_signature_not_corroborated() -> None:
    a, b = gen_key(), gen_key()
    r = _receipt(did_from_sk(a), did_from_sk(b))
    r["evidence"] = {"witness_signatures": [{"witness_did": did_from_sk(b), "signature": "not-base64!!"}]}
    assert is_corroborated(r) is False


def test_did_key_helpers_roundtrip_and_agree_with_identity() -> None:
    seed = gen_key()
    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    did = did_key_from_pubkey(pub)
    assert did == did_from_sk(seed)  # pubkey-form agrees with the seed-form deriver
    assert pubkey_from_did_key(did) == pub  # exact inverse
