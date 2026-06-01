"""Produce an ARP runtime's conformance badge — by consuming sm-conformance.

ARP does not mint its own badge mechanism (see ``spec/arp/0.1/conformance.md`` §2):
it *points at* `sm-conformance <https://github.com/Sharathvc23/sm-conformance>`_ for
the signed-badge envelope and verifier. This module is that relationship in code,
not just prose — ARP pins its own receipt-vector corpus and signs a badge with
sm-conformance's primitive, making ARP a real, importing first consumer.

Requires the ``conformance`` extra (``pip install 'sm-arp[conformance]'``), which
pulls in sm-conformance. Parsing and verifying receipts does not need it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sm_conformance.badge import compute_suite_digest, sign_envelope, verify_envelope

ARP_VECTORS = Path(__file__).resolve().parents[2] / "vectors" / "arp" / "0.1"
PROFILE_EXTENSION_KEY = "arp.conformance.profile"


def arp_suite_digest() -> str:
    """Pin the ARP receipt-vector corpus — the suite a badge attests passing."""
    return compute_suite_digest(ARP_VECTORS)


def build_arp_badge(
    runtime: str,
    *,
    passed: int,
    failed: int,
    skipped: int,
    signing_key32: bytes,
    signed_at: str,
    protocol_versions: tuple[str, ...] = ("0.1",),
) -> dict[str, Any]:
    """Sign a conformance badge for an ARP runtime, via sm-conformance.

    The badge pins the ARP vector corpus by ``suite_digest`` and carries the run
    counts. ``signed_at`` is RFC 3339 UTC; ``signing_key32`` is the runtime's own
    32-byte Ed25519 seed (the badge is self-signed — rung 1 of the trust ladder).
    """
    payload = {
        "schema_version": 1,
        "runtime": runtime,
        "protocol_versions": list(protocol_versions),
        "suite_digest": arp_suite_digest(),
        "completed_at": signed_at,
        "exit_status": 0 if failed == 0 else 1,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "xfailed": 0,
        "xpassed": 0,
        "total_vectors": passed + failed + skipped,
        "extensions": {PROFILE_EXTENSION_KEY: "receipts-0.1"},
    }
    return sign_envelope(payload, signing_key32, signed_at)


def verify_arp_badge(envelope: dict[str, Any]) -> dict[str, Any]:
    """Verify an ARP badge through sm-conformance's verifier; return the payload."""
    return verify_envelope(envelope)
