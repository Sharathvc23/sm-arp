"""`render` gives a receipt a readable one-liner without domain knowledge."""

from __future__ import annotations

from sm_arp import Identity, build_action, issue_receipt, render


def _owner() -> Identity:
    return Identity.from_seed(b"\x11" * 32)


def test_render_uses_date_and_summary() -> None:
    owner = _owner()
    receipt = issue_receipt(
        owner, principal_did=owner.did,
        action=build_action(category="authority_granted", human_summary="Publish your listing"),
    )
    line = render(receipt)
    assert "Publish your listing" in line
    assert line.startswith(receipt["issued_at"][:10])
    assert "(" not in line  # a completed outcome is not annotated


def test_render_annotates_non_completed_outcome() -> None:
    owner = _owner()
    receipt = issue_receipt(
        owner, principal_did=owner.did,
        action=build_action(
            category="data_shared", human_summary="Shared your profile", outcome="denied",
        ),
    )
    assert render(receipt).endswith("(denied)")


def test_render_tolerates_a_bare_receipt() -> None:
    # No action, no date — still returns something readable, never raises.
    assert render({}) == "receipt"
    assert render({"action": {"human_summary": "hi"}}) == "hi"
