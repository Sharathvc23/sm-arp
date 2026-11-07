"""sm-arp — the Agency Receipt Protocol, as a consumable library.

One canonical implementation of building, signing, and verifying ARP v0.1
receipts, plus a SQLite receipt log. Every runtime imports this rather than
vendoring its own copy, so the receipt envelope cannot drift between an issuer
(server side / Issuer Log) and a principal's agent (client side / Agency Log)
— drift is exactly what the conformance suite exists to catch.

    from sm_arp import Identity, build_action, issue_receipt, verify_receipt, IssuerLog

    me = Identity.generate()
    r = issue_receipt(me, principal_did=me.did,
                      action=build_action(category="data_shared", human_summary="…"))
    assert verify_receipt(r).ok
    IssuerLog("log.sqlite").append(r)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _dist_version

from .identity import Identity, did_from_sk, gen_key, pubkey_from_did
from .receipts import (
    ARP_VERSION,
    KNOWN_CATEGORIES,
    OUTCOMES,
    VerifyResult,
    build_action,
    canonical_bytes,
    chain_link,
    dat_digest,
    dat_grant_payload,
    issue_receipt,
    new_receipt_id,
    now_iso,
    render,
    verify_authority_chain,
    verify_direct_grant,
    verify_hash_chain,
    verify_receipt,
    verify_signature,
)
from .store import AgencyLog, IssuerLog, ReceiptLog

# Derived from installed distribution metadata, never hand-maintained.
#
# sm-arp previously exported no ``__version__`` at all, which is worse than a
# wrong one: ``getattr(sm_arp, "__version__", default)`` silently returns the
# CALLER's fallback, so a consumer's defensive version check reports whatever it
# guessed and looks like it succeeded. sm-arp is the most depended-on package in
# the org, so that silence propagated furthest.
#
# A literal would be a second copy of pyproject's ``version`` with nothing
# comparing them — the shape that shipped sm-provision 0.1.0 as "0.0.1" and
# sm-authority 0.1.0 as "0.0.1". Deriving it makes pyproject the single declared
# source and the installed wheel unable to misreport itself.
try:  # pragma: no cover - trivial branch, both sides asserted in tests
    __version__ = _dist_version("sm-arp")
except _PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0.dev0"

__all__ = [
    "ARP_VERSION",
    "KNOWN_CATEGORIES",
    "OUTCOMES",
    "AgencyLog",
    "Identity",
    "IssuerLog",
    "ReceiptLog",
    "VerifyResult",
    "__version__",
    "build_action",
    "canonical_bytes",
    "chain_link",
    "dat_digest",
    "dat_grant_payload",
    "did_from_sk",
    "gen_key",
    "issue_receipt",
    "new_receipt_id",
    "now_iso",
    "pubkey_from_did",
    "render",
    "verify_authority_chain",
    "verify_direct_grant",
    "verify_hash_chain",
    "verify_receipt",
    "verify_signature",
]
