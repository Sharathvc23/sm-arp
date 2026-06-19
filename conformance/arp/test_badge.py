"""ARP consumes sm-conformance for real — a badge round-trips through the primitive.

Skips when the ``conformance`` extra (sm-conformance) is not installed, so the core
receipt suite still runs without it. CI installs the extra, so this runs there.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sm_conformance")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance.arp.badge import (
    PROFILE_EXTENSION_KEY,
    arp_suite_digest,
    build_arp_badge,
    verify_arp_badge,
)

SIGNED_AT = "2026-06-01T00:00:00+00:00"


def _seed() -> bytes:
    return Ed25519PrivateKey.generate().private_bytes_raw()


def test_arp_badge_round_trips_through_sm_conformance() -> None:
    env = build_arp_badge(
        "arp-ref", passed=22, failed=0, skipped=0, signing_key32=_seed(), signed_at=SIGNED_AT
    )
    payload = verify_arp_badge(env)  # sm_conformance.verify_envelope under the hood
    assert payload["runtime"] == "arp-ref"
    assert payload["suite_digest"] == arp_suite_digest()
    assert payload["total_vectors"] == 22
    assert payload["extensions"][PROFILE_EXTENSION_KEY] == "receipts-0.1"


def test_suite_digest_pins_the_receipt_corpus() -> None:
    assert arp_suite_digest().startswith("sha256:")


def test_failing_run_sets_nonzero_exit_status() -> None:
    env = build_arp_badge(
        "arp-ref", passed=20, failed=2, skipped=0, signing_key32=_seed(), signed_at=SIGNED_AT
    )
    payload = verify_arp_badge(env)
    assert payload["exit_status"] == 1 and payload["total_vectors"] == 22
