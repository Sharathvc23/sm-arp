from datetime import UTC, datetime

from sm_arp import Identity, build_action, issue_receipt, verify_direct_grant


def test_direct_grant_checks_both_signatures_time_and_scope():
    owner, agent = Identity.generate(), Identity.generate()
    payload = {
        "granted_to_did": agent.did,
        "granted_scope": ["purchase"],
        "grant_expires_at": "2099-01-01T00:00:00Z",
    }
    grant = issue_receipt(
        owner,
        principal_did=owner.did,
        action=build_action(
            category="authority_granted", human_summary="approve", machine_payload=payload
        ),
    )
    action = issue_receipt(
        agent,
        principal_did=owner.did,
        action=build_action(
            category="purchase", human_summary="buy", granted_by_receipt_id=grant["receipt_id"]
        ),
    )
    now = datetime.now(UTC)
    assert verify_direct_grant(action, grant, at=now).ok
    assert not verify_direct_grant(action, grant, at=now, require_dat=True).ok
    assert not verify_direct_grant(action, grant, at=datetime(2099, 1, 1, tzinfo=UTC)).ok
    for item in (grant, action):
        forged = dict(item, signature="AA==")
        pair = (action, forged) if item is grant else (forged, grant)
        assert not verify_direct_grant(*pair, at=now).ok
