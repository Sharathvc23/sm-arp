"""Conformance for ``sm_arp.vrp`` AgentFacts attestation (VRP 0.2 §A/§B).

Pins ``facts_digest`` + ``build_attestation`` + ``verify_attestation`` so every
resolver establishes standing identically, and asserts byte-for-byte equality with
embedded golden values, so every resolver establishes standing identically.
"""

from __future__ import annotations

import copy

from sm_arp.vrp import build_attestation, facts_digest, verify_attestation

_SEED = bytes([7]) * 32
_AS_OF = "2026-01-01T00:00:00Z"
_FACTS = {
    "id": "did:key:zSubject",
    "verifiable_receipts": {"ledger_uri": "https://x/ledger", "behavioral_merkle_root": "sha256:abc"},
}
# Golden reference output for _FACTS signed by _SEED.
_GOLDEN_DIGEST = "sha256:0174e48f03bc02d7c931561c750a50c796e4452d4488642ad963be1e91028787"
_GOLDEN_ATTESTED_BY = "did:key:z6MkvDqGT54cXesYGvABpF1UapVNwjCqRcafi4Px6Thv5T3Z"
_GOLDEN_SIG = "GG8Xve54JF4Qsym9Wo8h6AAtKMrK9VsTRehDplON5oPnZNDT+K9PcCFwaxG9Wa0X6UxnW2BQmOXqW5kRqmQEDw=="


def _attested(**over):
    facts = copy.deepcopy(_FACTS)
    att = build_attestation(facts_record=facts, signing_key_bytes=_SEED, as_of=_AS_OF, **over)
    facts["attestation"] = att
    return facts


def test_golden_digest_and_signature_byte_for_byte() -> None:
    assert facts_digest(_FACTS) == _GOLDEN_DIGEST
    att = build_attestation(facts_record=copy.deepcopy(_FACTS), signing_key_bytes=_SEED, as_of=_AS_OF)
    assert att["attested_by"] == _GOLDEN_ATTESTED_BY
    assert att["signature"] == _GOLDEN_SIG


def test_build_verify_roundtrip_accepted() -> None:
    v = verify_attestation(_attested())
    assert v.ok is True and v.stage == "accepted"


def test_facts_digest_excludes_attestation_member() -> None:
    # The digest must be identical before and after the attestation is attached.
    facts = _attested()
    assert facts_digest(facts) == _GOLDEN_DIGEST


def test_tampered_record_digest_mismatch() -> None:
    facts = _attested()
    facts["id"] = "did:key:zAttacker"  # altered after signing
    v = verify_attestation(facts)
    assert v.ok is False and v.stage in ("facts_digest_mismatch", "subject_mismatch")


def test_tampered_signature_invalid() -> None:
    facts = _attested()
    facts["attestation"]["signature"] = "AAAA" + facts["attestation"]["signature"][4:]
    v = verify_attestation(facts)
    assert v.ok is False and v.stage == "attestation_invalid"


def test_no_facet_no_attestation_is_no_claim() -> None:
    v = verify_attestation({"id": "did:key:zX"})
    assert v.ok is True and v.stage == "no_claim"


def test_facet_without_attestation_missing() -> None:
    v = verify_attestation({"id": "did:key:zX", "verifiable_receipts": {"ledger_uri": "u"}})
    assert v.ok is False and v.stage == "attestation_missing"


def test_revoked_lifecycle_rejected() -> None:
    v = verify_attestation(_attested(lifecycle="revoked"))
    assert v.ok is False and v.stage == "revoked"


def test_stale_version_rejected() -> None:
    facts = _attested(version=2)
    assert verify_attestation(facts, min_version=2).ok is True
    v = verify_attestation(facts, min_version=3)
    assert v.ok is False and v.stage == "stale_attestation"


def test_facet_binding_mismatch() -> None:
    facts = _attested()
    facts["verifiable_receipts"]["ledger_uri"] = "https://evil/ledger"  # swap facet after signing
    v = verify_attestation(facts)
    # digest covers the facet too, so this trips the digest check first — either way, rejected.
    assert v.ok is False and v.stage in ("facts_digest_mismatch", "facet_binding_mismatch")
