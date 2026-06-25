"""DAT bridge (§4.5 / DAT SPEC §9.1): an ``authority_granted`` receipt that
references a Delegated Authority Token by id + digest, resolved and richly
evaluated through ``verify_authority_chain``'s opt-in hooks.

sm-arp does not import sm-dat — the rich evaluator is injected. These tests use a
tiny fake DAT and a fake verifier to exercise the bridge in isolation.
"""

from __future__ import annotations

from typing import Any

from sm_arp import (
    Identity,
    VerifyResult,
    build_action,
    dat_digest,
    dat_grant_payload,
    issue_receipt,
    verify_authority_chain,
)

HUMAN = Identity.from_seed(b"h" * 32)
AGENT = Identity.from_seed(b"a" * 32)


def fake_dat() -> dict[str, Any]:
    """A minimal DAT-shaped envelope (sm-dat would produce the real thing)."""
    return {
        "version": "dat/0.1",
        "grant_id": "dat:demo:movies",
        "grantor_did": HUMAN.did,
        "grantee_did": AGENT.did,
        "not_after": "2026-12-31T23:59:59Z",
        "scope": {"action_categories": ["purchase"]},
        "signature": "AA==",
    }


def grant_receipt(dat: dict[str, Any]) -> dict[str, Any]:
    """Human issues an ``authority_granted`` receipt referencing the DAT."""
    return issue_receipt(
        HUMAN,
        principal_did=HUMAN.did,
        action=build_action(
            category="authority_granted",
            human_summary="Granted the movies DAT.",
            machine_payload=dat_grant_payload(dat),
        ),
    )


def action_receipt(grant_id: str) -> dict[str, Any]:
    """Agent acts under the grant."""
    return issue_receipt(
        AGENT,
        principal_did=HUMAN.did,
        action=build_action(
            category="purchase",
            human_summary="2 tickets",
            granted_by_receipt_id=grant_id,
        ),
    )


def test_thin_path_unchanged_without_opt_in():
    dat = fake_dat()
    g = grant_receipt(dat)
    r = action_receipt(g["receipt_id"])
    # No dats / dat_verifier → pre-bridge behaviour: thin scope check passes.
    assert verify_authority_chain(r, {g["receipt_id"]: g}).ok


def test_digest_match_and_rich_verifier_called():
    dat = fake_dat()
    g = grant_receipt(dat)
    r = action_receipt(g["receipt_id"])
    seen: list[str] = []

    def verifier(d: dict[str, Any], rec: dict[str, Any]) -> VerifyResult:
        seen.append(d["grant_id"])
        return VerifyResult.accepted()

    res = verify_authority_chain(
        r, {g["receipt_id"]: g}, dats={dat["grant_id"]: dat}, dat_verifier=verifier
    )
    assert res.ok
    assert seen == ["dat:demo:movies"]  # the injected evaluator ran


def test_rich_verifier_rejection_propagates():
    dat = fake_dat()
    g = grant_receipt(dat)
    r = action_receipt(g["receipt_id"])

    def deny(d: dict[str, Any], rec: dict[str, Any]) -> VerifyResult:
        return VerifyResult(False, "authority_chain", "amount_cap_exceeded")

    res = verify_authority_chain(
        r, {g["receipt_id"]: g}, dats={dat["grant_id"]: dat}, dat_verifier=deny
    )
    assert not res.ok and res.detail == "amount_cap_exceeded"


def test_digest_mismatch_rejected():
    dat = fake_dat()
    g = grant_receipt(dat)
    r = action_receipt(g["receipt_id"])
    tampered = dict(dat, not_after="2099-01-01T00:00:00Z")  # different bytes → different digest
    res = verify_authority_chain(r, {g["receipt_id"]: g}, dats={dat["grant_id"]: tampered})
    assert not res.ok and "dat_digest" in res.detail


def test_scope_disagreement_rejected():
    # Receipt commits the correct DAT digest but a tampered thin granted_scope
    # that widens past the DAT's categories. Digest matches; scope must not drift.
    dat = fake_dat()
    mp = dat_grant_payload(dat)
    mp["granted_scope"] = ["purchase", "payment_sent"]  # disagrees with DAT's ["purchase"]
    g = issue_receipt(
        HUMAN,
        principal_did=HUMAN.did,
        action=build_action(
            category="authority_granted",
            human_summary="Granted, scope tampered.",
            machine_payload=mp,
        ),
    )
    r = action_receipt(g["receipt_id"])
    res = verify_authority_chain(r, {g["receipt_id"]: g}, dats={dat["grant_id"]: dat})
    assert not res.ok and "disagrees" in res.detail


def test_referenced_but_not_provided():
    dat = fake_dat()
    g = grant_receipt(dat)
    r = action_receipt(g["receipt_id"])

    def verifier(d: dict[str, Any], rec: dict[str, Any]) -> VerifyResult:
        return VerifyResult.accepted()

    res = verify_authority_chain(r, {g["receipt_id"]: g}, dat_verifier=verifier)
    assert not res.ok and "not provided" in res.detail


def test_digest_helpers_roundtrip():
    dat = fake_dat()
    mp = dat_grant_payload(dat)
    assert mp["dat_grant_id"] == "dat:demo:movies"
    assert mp["dat_digest"] == dat_digest(dat)
    assert mp["granted_scope"] == ["purchase"]
