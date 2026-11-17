"""Verifier MUSTs: ``issued_at`` freshness (spec §3.3, §6.3 step 6) and the
reversal-issuer rule (spec §4.2).

FRESHNESS   checked against a caller-supplied reference instant (``now``); old
            receipts still verify for audit when no ``now`` is given
REVERSAL    a reversal's issuer must equal the issuer of the original it
            reverses, checked against originals the verifier holds
HOSTILE     crafted receipts and misleading arguments fail (or raise, for
            programming errors) instead of being accepted
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from sm_arp import (
    DEFAULT_MAX_SKEW_SECONDS,
    Identity,
    build_action,
    canonical_bytes,
    issue_receipt,
    verify_direct_grant,
    verify_freshness,
    verify_receipt,
    verify_reversal,
)

T0 = datetime(2026, 5, 21, 14, 23, 1, tzinfo=UTC)
T0_ISO = "2026-05-21T14:23:01Z"


def _receipt(issuer: Identity | None = None, **kw: Any) -> dict[str, Any]:
    issuer = issuer or Identity.generate()
    kw.setdefault("issued_at", T0_ISO)
    kw.setdefault("action", build_action(category="message_sent", human_summary="Sent it."))
    return issue_receipt(issuer, principal_did=issuer.did, **kw)


def _signed_raw(issuer: Identity, body: dict[str, Any]) -> dict[str, Any]:
    """Sign an arbitrary body (bypassing issue_receipt's input checks), as a hostile
    issuer could."""
    out = dict(body)
    out["signature"] = base64.b64encode(
        issuer.sign(canonical_bytes(out, include_signature=False))
    ).decode("ascii")
    return out


# ── freshness ─────────────────────────────────────────────────────────


def test_default_verification_applies_no_window_so_old_receipts_stay_auditable() -> None:
    r = _receipt(issued_at="1999-01-01T00:00:00Z")
    assert verify_receipt(r).ok
    assert verify_receipt(r, now=datetime.now(UTC)).stage == "freshness"


@pytest.mark.parametrize(
    ("offset", "ok"),
    [(0, True), (-300, True), (300, True), (-301, False), (301, False), (-86400, False)],
)
def test_window_is_inclusive_and_symmetric(offset: int, ok: bool) -> None:
    """``now`` = T0 + offset. A negative offset puts ``now`` before issuance, so the
    receipt looks forward-dated; a positive one makes it stale."""
    res = verify_receipt(_receipt(), now=T0 + timedelta(seconds=offset))
    assert res.ok is ok, res
    if not ok:
        assert res.stage == "freshness"
        assert ("forward-dated" if offset < 0 else "stale") in res.detail


def test_default_window_is_300_seconds() -> None:
    assert DEFAULT_MAX_SKEW_SECONDS == 300


def test_custom_window_including_zero() -> None:
    r = _receipt()
    assert verify_receipt(r, now=T0 + timedelta(seconds=30), max_skew_seconds=60).ok
    assert not verify_receipt(r, now=T0 + timedelta(seconds=61), max_skew_seconds=60).ok
    assert verify_receipt(r, now=T0, max_skew_seconds=0).ok
    assert not verify_receipt(r, now=T0 + timedelta(seconds=1), max_skew_seconds=0).ok


def test_reference_instant_in_another_offset_is_compared_as_an_instant() -> None:
    """``now`` in +05:30 that is the same instant as issued_at is in the window."""
    ist = timezone(timedelta(hours=5, minutes=30))
    assert verify_receipt(_receipt(), now=T0.astimezone(ist)).ok


def test_issued_at_with_an_offset_is_compared_as_an_instant() -> None:
    """A hostile issuer can sign a non-``Z`` issued_at (the library's structural stage
    does not pin the §3.1 format). Freshness still compares the instant it names,
    not the string: 19:53:01+05:30 is 14:23:01Z."""
    issuer = Identity.generate()
    body = {
        "version": "arp/0.1",
        "receipt_id": "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f",
        "issuer_did": issuer.did,
        "principal_did": issuer.did,
        "issued_at": "2026-05-21T19:53:01+05:30",
        "action": build_action(category="message_sent", human_summary="Sent it."),
    }
    r = _signed_raw(issuer, body)
    assert verify_receipt(r, now=T0).ok
    assert not verify_receipt(r, now=T0 + timedelta(hours=5, minutes=30)).ok


@pytest.mark.parametrize(
    "issued_at",
    ["2026-05-21T14:23:01", "yesterday", "", "2026-13-45T99:99:99Z", 1716301381, None, ["x"]],
)
def test_signed_receipt_with_unparseable_issued_at_fails_freshness(issued_at: object) -> None:
    """The issuer signed the garbage, so the signature stage passes; freshness must
    fail rather than raise or accept."""
    issuer = Identity.generate()
    body = {
        "version": "arp/0.1",
        "receipt_id": "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f",
        "issuer_did": issuer.did,
        "principal_did": issuer.did,
        "issued_at": issued_at,
        "action": build_action(category="message_sent", human_summary="Sent it."),
    }
    r = _signed_raw(issuer, body)
    assert verify_receipt(r).ok  # no reference instant: freshness not evaluated
    res = verify_receipt(r, now=T0)
    assert (res.ok, res.stage) == (False, "freshness")


def test_freshness_runs_after_the_signature() -> None:
    """A tampered receipt reports its signature failure, not a freshness verdict."""
    r = _receipt()
    r["action"]["human_summary"] = "Rewritten."
    assert verify_receipt(r, now=T0 + timedelta(days=9)).stage == "signature"


def test_huge_window_does_not_overflow() -> None:
    assert verify_receipt(_receipt(), now=datetime.now(UTC), max_skew_seconds=10**30).ok


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"now": datetime(2026, 5, 21, 14, 23, 1)}, "timezone-aware"),
        ({"now": T0_ISO}, "timezone-aware"),
        ({"now": 1716301381}, "timezone-aware"),
        ({"now": T0, "max_skew_seconds": -1}, "non-negative int"),
        ({"now": T0, "max_skew_seconds": True}, "non-negative int"),
        ({"now": T0, "max_skew_seconds": 300.0}, "non-negative int"),
        ({"now": T0, "max_skew_seconds": float("nan")}, "non-negative int"),
        ({"now": T0, "max_skew_seconds": float("inf")}, "non-negative int"),
        ({"now": T0, "max_skew_seconds": "300"}, "non-negative int"),
        ({"max_skew_seconds": 60}, "without now"),
    ],
)
def test_arguments_that_would_mislead_raise(kwargs: dict[str, Any], match: str) -> None:
    """A naive or non-datetime reference, a nonsense window, or a window with no
    reference instant (which would look like a check that never runs) are caller
    bugs and raise, even for a receipt that would otherwise verify."""
    with pytest.raises(ValueError, match=match):
        verify_receipt(_receipt(), **kwargs)


def test_verify_freshness_directly() -> None:
    r = _receipt()
    assert verify_freshness(r, now=T0).ok
    assert verify_freshness(r, now=T0 + timedelta(seconds=301)).stage == "freshness"
    with pytest.raises(ValueError):
        verify_freshness(r, now=datetime(2026, 5, 21))


def test_verify_direct_grant_is_unaffected() -> None:
    """verify_direct_grant authenticates a grant issued long before ``at`` through
    verify_receipt; the opt-in window must not leak into it."""
    grantor, agent = Identity.generate(), Identity.generate()
    grant = issue_receipt(
        grantor,
        principal_did=grantor.did,
        issued_at="2020-01-01T00:00:00Z",
        action=build_action(
            category="authority_granted",
            human_summary="Granted.",
            machine_payload={
                "granted_to_did": agent.did,
                "granted_scope": ["data_shared"],
                "grant_expires_at": "2099-01-01T00:00:00Z",
            },
        ),
    )
    action = issue_receipt(
        agent,
        principal_did=grantor.did,
        issued_at="2021-01-01T00:00:00Z",
        action=build_action(
            category="data_shared",
            human_summary="Shared.",
            granted_by_receipt_id=grant["receipt_id"],
        ),
    )
    assert verify_direct_grant(action, grant, at=datetime(2022, 1, 1, tzinfo=UTC)).ok


# ── reversal issuer (§4.2) ──────────────────────────────────────────────


def _reversal(issuer: Identity, original: dict[str, Any], **kw: Any) -> dict[str, Any]:
    action = build_action(category="purchase", human_summary="Refunded it.", outcome="reversed")
    action["reversal_of_receipt_id"] = original["receipt_id"]
    return issue_receipt(issuer, principal_did=original["principal_did"], action=action, **kw)


@pytest.fixture
def merchant_agent() -> Identity:
    return Identity.generate()


@pytest.fixture
def purchase(merchant_agent: Identity) -> dict[str, Any]:
    return issue_receipt(
        merchant_agent,
        principal_did=Identity.generate().did,
        action=build_action(category="purchase", human_summary="Bought it.", amount_cents=-3450),
    )


def test_same_issuer_reversal_verifies(merchant_agent: Identity, purchase: dict[str, Any]) -> None:
    rev = _reversal(merchant_agent, purchase)
    assert verify_receipt(rev, originals={purchase["receipt_id"]: purchase}).ok


def test_reversal_by_another_issuer_is_rejected(purchase: dict[str, Any]) -> None:
    rev = _reversal(Identity.generate(), purchase)
    assert verify_receipt(rev).ok  # opt-in: without originals the rule is not evaluated
    res = verify_receipt(rev, originals={purchase["receipt_id"]: purchase})
    assert (res.ok, res.stage) == (False, "reversal")
    assert "not the issuer" in res.detail


def test_reversal_whose_original_is_not_held_is_not_evaluated(purchase: dict[str, Any]) -> None:
    """The rule needs the original; a verifier that does not hold it cannot apply it.
    A caller that requires the original checks membership itself."""
    rev = _reversal(Identity.generate(), purchase)
    assert verify_receipt(rev, originals={}).ok
    other = _receipt()
    assert verify_receipt(rev, originals={other["receipt_id"]: other}).ok


def test_non_reversal_receipts_are_untouched(purchase: dict[str, Any]) -> None:
    assert verify_receipt(purchase, originals={purchase["receipt_id"]: purchase}).ok


def test_original_is_authenticated_before_its_issuer_is_trusted(
    merchant_agent: Identity, purchase: dict[str, Any]
) -> None:
    """An attacker who can write to the verifier's index cannot relabel the original
    as its own: the original's signature binds its issuer_did."""
    attacker = Identity.generate()
    rev = _reversal(attacker, purchase)
    relabelled = {**purchase, "issuer_did": attacker.did}
    res = verify_receipt(rev, originals={purchase["receipt_id"]: relabelled})
    assert (res.ok, res.stage) == (False, "reversal")
    assert "signature" in res.detail
    tampered = {**purchase, "action": {**purchase["action"], "human_summary": "Bought more."}}
    rev = _reversal(merchant_agent, purchase)
    res = verify_receipt(rev, originals={tampered["receipt_id"]: tampered})
    assert (res.ok, res.stage) == (False, "reversal")


def test_index_key_must_be_the_originals_receipt_id(
    merchant_agent: Identity, purchase: dict[str, Any]
) -> None:
    """Substitution: the verifier's index maps the referenced id to a different
    (validly signed, same-issuer) receipt."""
    decoy = issue_receipt(
        merchant_agent,
        principal_did=purchase["principal_did"],
        action=build_action(category="purchase", human_summary="Bought a decoy."),
    )
    rev = _reversal(merchant_agent, purchase)
    res = verify_reversal(rev, {purchase["receipt_id"]: decoy})
    assert (res.ok, res.stage) == (False, "reversal")


def test_receipt_cannot_reverse_itself() -> None:
    issuer = Identity.generate()
    action = build_action(category="purchase", human_summary="Refunded it.", outcome="reversed")
    rid = "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a"
    action["reversal_of_receipt_id"] = rid
    r = issue_receipt(issuer, principal_did=issuer.did, action=action, receipt_id=rid)
    assert verify_receipt(r, originals={}).stage == "reversal"
    assert verify_receipt(r, originals={rid: r}).stage == "reversal"


@pytest.mark.parametrize("ref", [["x"], {"id": "x"}, "", 7, None, True])
def test_non_string_reversal_reference_fails_without_raising(ref: object) -> None:
    """A signed receipt with an unhashable/empty reference must fail at the reversal
    stage, not raise TypeError from the index lookup."""
    issuer = Identity.generate()
    action = build_action(category="purchase", human_summary="Refunded it.", outcome="reversed")
    action["reversal_of_receipt_id"] = ref
    r = issue_receipt(issuer, principal_did=issuer.did, action=action)
    res = verify_receipt(r, originals={"x": _receipt(issuer)})
    assert (res.ok, res.stage) == (False, "reversal")


@pytest.mark.parametrize("held", [["not", "a", "receipt"], "receipt", None, 7])
def test_non_object_original_fails(
    merchant_agent: Identity, purchase: dict[str, Any], held: object
) -> None:
    rev = _reversal(merchant_agent, purchase)
    res = verify_reversal(rev, {purchase["receipt_id"]: held})  # type: ignore[dict-item]
    assert (res.ok, res.stage) == (False, "reversal")


def test_reversal_stage_runs_after_signature_and_freshness(purchase: dict[str, Any]) -> None:
    rev = _reversal(Identity.generate(), purchase, issued_at=T0_ISO)
    originals = {purchase["receipt_id"]: purchase}
    assert verify_receipt(rev, originals=originals, now=T0 + timedelta(hours=1)).stage == (
        "freshness"
    )
    rev["action"]["human_summary"] = "Rewritten."
    assert verify_receipt(rev, originals=originals).stage == "signature"
