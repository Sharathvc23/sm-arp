"""End-to-end demonstration of the full ARP / VRP capability set.

Run from a checkout::

    uv run python examples/full_set_demo.py

Every value printed is computed live against the installed ``sm_arp`` package;
nothing is hard-coded. The demo exercises, in order:

1. Pricing on an action (``action.amount``) + real Ed25519 signing.
2. Per-issuer hash-chained receipts (and tamper detection).
3. Counterparty corroboration (a co-signature that cannot be self-fabricated).
4. ``nanda-rep`` reputation scoring with collusion-ring severance.
5. The behavioral Merkle root (a tamper-evident ledger commitment).
6. The ``verifiable_receipts`` AgentFacts facet + ledger recomputation.
7. Authority-signed attestation over a facts record.

This is the *full engine*. Trust-layer adapters (e.g. a Nanda Town ``trust``
plugin) typically surface only the scoring; the receipt lifecycle below —
pricing, chaining, the facet, attestation — lives here in ``sm_arp``.
"""

from __future__ import annotations

import json
from typing import Any

from sm_arp.identity import Identity
from sm_arp.receipts import (
    build_action,
    chain_link,
    issue_receipt,
    verify_hash_chain,
    verify_receipt,
)
from sm_arp.vrp import (
    DEFAULT_CATEGORY_WEIGHTS,
    behavioral_merkle_root,
    build_attestation,
    build_ledger,
    corroboration_rate,
    cosign_receipt,
    facet_from_ledger,
    is_corroborated,
    reputation_score,
    reputation_score_v2,
    verify_attestation,
    verify_ledger,
)


def _banner(title: str) -> None:
    print("\n" + "=" * 68 + "\n" + title + "\n" + "=" * 68)


def _valid(_receipt: dict[str, Any]) -> bool:
    """Validity oracle for scoring.

    sm-arp's scoring takes the validity check as a parameter so each resolver
    can plug in its own policy. Here every hand-built receipt is treated as
    valid; in production you would pass ``lambda r: verify_receipt(r).ok``.
    """
    return True


def _corroborated(issuer: Identity, cp_seed: bytes, cp: Identity, rid: str) -> dict[str, Any]:
    """A receipt co-signed by its counterparty, so ``is_corroborated`` holds."""
    receipt: dict[str, Any] = {
        "version": "arp/0.1",
        "receipt_id": rid,
        "issuer_did": issuer.did,
        "issued_at": "2026-01-01T00:00:00Z",
        "action": build_action(
            category="purchase", human_summary="x", counterparty_did=cp.did
        ),
    }
    receipt["evidence"] = {"witness_signatures": [cosign_receipt(receipt, signing_key_bytes=cp_seed)]}
    return receipt


def main() -> None:
    alice = Identity.from_seed(bytes([1]) * 32)
    bob = Identity.from_seed(bytes([2]) * 32)
    print("alice:", alice.did)
    print("bob  :", bob.did)

    _banner("1. Pricing + real Ed25519 signing + verification")
    action = build_action(
        category="purchase",
        human_summary="Bought movie ticket",
        counterparty_did=bob.did,
        counterparty_label="MovieCo",
        amount_cents=1850,
        currency="USD",
    )
    r1 = issue_receipt(
        alice, principal_did=alice.did, action=action, issued_at="2026-01-01T00:00:00Z"
    )
    print("action.amount:", r1["action"]["amount"], "category:", r1["action"]["category"])
    print("verify_receipt(r1).ok =", verify_receipt(r1).ok)

    _banner("2. Hash-chained receipts (per-issuer chain)")
    action2 = build_action(
        category="payment_sent",
        human_summary="Paid for ticket",
        counterparty_did=bob.did,
        amount_cents=1850,
        currency="USD",
    )
    prev = chain_link(r1)
    r2 = issue_receipt(
        alice,
        principal_did=alice.did,
        action=action2,
        previous_receipt_hash=prev,
        issued_at="2026-01-01T00:01:00Z",
    )
    print("chain_link(r1)           =", prev)
    print("r2.previous_receipt_hash =", r2["previous_receipt_hash"])
    print("verify_hash_chain(r2, r1).ok           =", verify_hash_chain(r2, r1).ok)
    tampered = json.loads(json.dumps(r1))
    tampered["action"]["amount"]["cents"] = 1
    print("verify_hash_chain(r2, tampered r1).ok  =", verify_hash_chain(r2, tampered).ok)

    _banner("3. Corroboration (counterparty co-signature)")
    base: dict[str, Any] = {
        "version": "arp/0.1",
        "receipt_id": "fixed",
        "issuer_did": alice.did,
        "issued_at": "2026-01-01T00:00:00Z",
        "action": build_action(
            category="purchase", human_summary="x", counterparty_did=bob.did, amount_cents=5000
        ),
    }
    print("before counterparty cosign -> is_corroborated =", is_corroborated(base))
    base["evidence"] = {"witness_signatures": [cosign_receipt(base, signing_key_bytes=bytes([2]) * 32)]}
    print("after counterparty cosign  -> is_corroborated =", is_corroborated(base))

    _banner("4. Reputation scoring (nanda-rep) + collusion severance")
    seeds = {n: bytes([i]) * 32 for n, i in zip("ABCXY", (1, 2, 3, 10, 11), strict=True)}
    who = {n: Identity.from_seed(s) for n, s in seeds.items()}
    ring = [
        _corroborated(who["A"], seeds["B"], who["B"], "ab"),
        _corroborated(who["B"], seeds["C"], who["C"], "bc"),
        _corroborated(who["C"], seeds["A"], who["A"], "ca"),
    ]  # honest 3-ring = the anchor
    pair = [
        _corroborated(who["X"], seeds["Y"], who["Y"], "xy"),
        _corroborated(who["Y"], seeds["X"], who["X"], "yx"),
    ]  # isolated collusion pair = wash trading
    receipts = ring + pair
    print("reputation_score    (ungated):", reputation_score(receipts, is_valid=_valid))
    print(
        "reputation_score_v2 (severed):",
        reputation_score_v2(receipts, is_valid=_valid),
        "<- collusion pair removed",
    )
    print("corroboration_rate:", corroboration_rate(receipts, is_valid=_valid))
    print(
        "category weights -> purchase:",
        DEFAULT_CATEGORY_WEIGHTS.get("purchase"),
        "payment_sent:",
        DEFAULT_CATEGORY_WEIGHTS.get("payment_sent"),
    )

    _banner("5. Behavioral Merkle root (tamper-evident commitment)")
    print("root(ring)                =", behavioral_merkle_root(ring))
    print("root(reversed order)      =", behavioral_merkle_root(ring[::-1]), "(order-canonical)")
    mutated = json.loads(json.dumps(ring))
    mutated[0]["action"]["human_summary"] = "TAMPERED"
    print("root(one receipt mutated) =", behavioral_merkle_root(mutated), "(changes)")

    _banner("6. verifiable_receipts facet (AgentFacts) + recomputation")
    ledger = build_ledger(
        subject=who["A"].did, receipts=ring, is_valid=_valid, as_of="2026-01-02T00:00:00Z"
    )
    facet = facet_from_ledger(ledger, ledger_uri="https://vault.example.org/ledgers/alice")
    print(json.dumps(facet, indent=2))
    print("verify_ledger(ledger).ok =", verify_ledger(ledger, is_valid=_valid).ok)

    _banner("7. Attestation (authority-signed standing)")
    facts: dict[str, Any] = {"id": who["A"].did, "verifiable_receipts": facet}
    facts["attestation"] = build_attestation(
        facts_record=facts, signing_key_bytes=seeds["A"], as_of="2026-01-02T00:00:00Z"
    )
    print("verify_attestation(facts).ok =", verify_attestation(facts).ok)


if __name__ == "__main__":
    main()
