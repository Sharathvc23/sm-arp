"""sm_arp consumable library — build / sign / verify / store.

ROUND-TRIP   issue → verify accepts
TAMPER       any post-sign mutation fails at the signature stage
HASH-CHAIN   linked receipts verify; a broken link is rejected
AUTHORITY    a granted action verifies; out-of-scope is rejected
STORE        append → query round-trips; idempotent on (issuer, receipt_id)
CORPUS       verify_receipt agrees with every canonical vector's documented verdict
NO-DRIFT     verify_receipt agrees with the conformance verifier on every vector

Round-trip is *circular* — issue and verify share canonical_bytes(), so a
canonicalization bug passes both sides. The corpus + no-drift tests are the
load-bearing ones: they run the lib's verifier against receipts it did NOT
produce (the spec's own vectors), where canonicalization bugs actually live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from sm_arp import (
    Identity,
    IssuerLog,
    VerifyResult,
    build_action,
    chain_link,
    issue_receipt,
    verify_receipt,
)

# The spec's language-agnostic vector corpus lives at <repo>/vectors/arp/0.1.
_VECTORS_DIR = Path(__file__).resolve().parents[2] / "vectors" / "arp" / "0.1"
_VECTOR_PATHS = sorted(_VECTORS_DIR.glob("*.json"))


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _chain_priors() -> dict[str, dict[str, Any]]:
    """{chain_link(receipt): receipt} over passing vectors, so a vector that
    declares a previous_receipt_hash can resolve its predecessor — mirrors
    conformance/arp/test_arp_v01.py's chain_priors fixture."""
    priors: dict[str, dict[str, Any]] = {}
    for p in _VECTOR_PATHS:
        v = _load(p)
        if v["expected_outcome"] == "verify_pass":
            priors[chain_link(v["receipt"])] = v["receipt"]
    return priors


def _verify_vector(v: dict[str, Any], priors: dict[str, dict[str, Any]]) -> VerifyResult:
    """Run sm_arp.verify_receipt over a vector, resolving its hash-chain prior
    the way a real consumer would (look the declared link up in what it's seen)."""
    receipt = v["receipt"]
    declared = receipt.get("previous_receipt_hash")
    return verify_receipt(
        receipt,
        mode=v.get("verifier_mode", "strict"),
        prior=priors.get(declared) if declared else None,
        check_chain=bool(declared),
    )


def _action(
    category: str = "data_shared", summary: str = "did a thing", **kw: Any
) -> dict[str, Any]:
    return build_action(category=category, human_summary=summary, **kw)


def test_issue_verify_round_trip() -> None:
    me = Identity.generate()
    r = issue_receipt(me, principal_did=me.did, action=_action())
    res = verify_receipt(r)
    assert res.ok, res


def test_tamper_fails_at_signature() -> None:
    me = Identity.generate()
    r = issue_receipt(me, principal_did=me.did, action=_action())
    r["action"]["human_summary"] = "rewritten after signing"
    res = verify_receipt(r)
    assert not res.ok and res.stage == "signature"


def test_hash_chain_links_and_breaks() -> None:
    me = Identity.generate()
    r1 = issue_receipt(me, principal_did=me.did, action=_action())
    r2 = issue_receipt(
        me, principal_did=me.did, action=_action(), previous_receipt_hash=chain_link(r1)
    )
    assert verify_receipt(r2, prior=r1, check_chain=True).ok
    # wrong prior → mismatch
    other = issue_receipt(me, principal_did=me.did, action=_action())
    assert verify_receipt(r2, prior=other, check_chain=True).stage == "hash_chain"
    # genesis must not declare a previous hash
    assert verify_receipt(r2, prior=None, check_chain=True).stage == "hash_chain"


def test_authority_chain_scope() -> None:
    grantor = Identity.generate()
    agent = Identity.generate()
    principal = grantor.did
    grant = issue_receipt(
        grantor,
        principal_did=principal,
        action=build_action(
            category="authority_granted",
            human_summary="granted",
            machine_payload={"granted_to_did": agent.did, "granted_scope": ["data_shared"]},
        ),
    )
    grants = {grant["receipt_id"]: grant}
    ok = issue_receipt(
        agent,
        principal_did=principal,
        action=_action(category="data_shared", granted_by_receipt_id=grant["receipt_id"]),
    )
    assert verify_receipt(ok, grants=grants).ok
    out_of_scope = issue_receipt(
        agent,
        principal_did=principal,
        action=_action(category="purchase", granted_by_receipt_id=grant["receipt_id"]),
    )
    assert verify_receipt(out_of_scope, grants=grants).stage == "authority_chain"


def test_store_round_trip_and_idempotent(tmp_path: Path) -> None:
    log = IssuerLog(tmp_path / "log.sqlite")
    me = Identity.generate()
    other = Identity.generate()
    r = issue_receipt(me, principal_did=other.did, action=_action())
    link = log.append(r)
    assert link == chain_link(r)
    log.append(r)  # idempotent on (issuer, receipt_id)
    assert log.count() == 1
    assert log.list_for_principal(other.did)[0]["receipt_id"] == r["receipt_id"]
    assert log.list_for_issuer(me.did)[0]["receipt_id"] == r["receipt_id"]
    stored = log.get(r["receipt_id"])
    assert stored is not None
    assert stored["signature"] == r["signature"]


def _schema_categories() -> set[str]:
    """The category enum from the normative JSON schema — the source of truth the
    conformance harness gates strict verification on."""
    schema = _load(_VECTORS_DIR.parents[2] / "schema" / "arp" / "0.1" / "action.schema.json")
    return set(schema["properties"]["category"]["enum"])


def test_category_enumerations_agree() -> None:
    """The three category enumerations MUST be the same set: the normative schema
    enum, the lib's strict KNOWN_CATEGORIES, and vrp's DEFAULT_CATEGORY_WEIGHTS.

    This is the invariant the commitment_* drift violated (KNOWN_CATEGORIES had
    dropped commitment_entered/fulfilled/breached while the schema and the scorer
    still carried them). Locking all three together permanently prevents the next
    silent divergence between what a receipt can declare, what verifies, and what
    the reputation scorer rewards."""
    from sm_arp.receipts import KNOWN_CATEGORIES
    from sm_arp.vrp import DEFAULT_CATEGORY_WEIGHTS

    schema_cats = _schema_categories()
    assert set(KNOWN_CATEGORIES) == schema_cats, (
        f"KNOWN_CATEGORIES drift: only-in-schema={schema_cats - set(KNOWN_CATEGORIES)}, "
        f"only-in-known={set(KNOWN_CATEGORIES) - schema_cats}"
    )
    assert set(DEFAULT_CATEGORY_WEIGHTS) == schema_cats, (
        f"weights drift: only-in-schema={schema_cats - set(DEFAULT_CATEGORY_WEIGHTS)}, "
        f"only-in-weights={set(DEFAULT_CATEGORY_WEIGHTS) - schema_cats}"
    )


@pytest.mark.parametrize(
    "category", ["commitment_entered", "commitment_fulfilled", "commitment_breached"]
)
def test_commitment_receipt_verifies_and_scores(category: str) -> None:
    """A commitment receipt must pass STRICT verification (it is a valid v0.1
    category) and be a known category to the reputation scorer. Before the fix a
    strict verifier rejected it at the structure stage while the scorer weighted
    it — a receipt that scored could not verify."""
    from sm_arp.receipts import KNOWN_CATEGORIES
    from sm_arp.vrp import DEFAULT_CATEGORY_WEIGHTS, reputation_score

    me = Identity.generate()
    r = issue_receipt(me, principal_did=me.did, action=_action(category=category))
    res = verify_receipt(r, mode="strict")
    assert res.ok, f"strict verify rejected {category}: {res.stage}: {res.detail}"

    assert category in KNOWN_CATEGORIES
    assert category in DEFAULT_CATEGORY_WEIGHTS
    # The scorer must see the same weight the published table declares for it.
    score = reputation_score([r], is_valid=lambda _: True)
    assert score == DEFAULT_CATEGORY_WEIGHTS[category]


@pytest.mark.parametrize("path", _VECTOR_PATHS, ids=lambda p: p.stem)
def test_verify_matches_vector_corpus(path: Path) -> None:
    """The lib's verifier must reproduce each canonical vector's documented
    verdict. This is the real proof — these receipts the lib did NOT issue, so
    a canonicalization or structural bug surfaces here, not in round-trip."""
    v = _load(path)
    expect_pass = v["expected_outcome"] == "verify_pass"
    res = _verify_vector(v, _chain_priors())
    assert res.ok is expect_pass, (
        f"{v['id']}: expected ok={expect_pass}, got {res.stage}: {res.detail}"
    )


def test_corpus_is_present() -> None:
    """Guard against an empty glob silently turning the corpus test into a no-op."""
    assert len(_VECTOR_PATHS) >= 20, f"only {len(_VECTOR_PATHS)} vectors found at {_VECTORS_DIR}"


@pytest.mark.parametrize("path", _VECTOR_PATHS, ids=lambda p: p.stem)
def test_verify_agrees_with_conformance(path: Path) -> None:
    """The lib's verdict must equal the conformance harness's verdict on every
    vector — the two independent verify impls cannot disagree. The import is
    HARD on purpose: if conformance ever stops importing, this must fail, not
    skip (a silent skip is exactly the drift this repo exists to prevent)."""
    from conformance.arp import verify_receipt as conf_verify

    v = _load(path)
    priors = {
        chain_link(_load(p)["receipt"]): _load(p)["receipt"]
        for p in _VECTOR_PATHS
        if _load(p)["expected_outcome"] == "verify_pass"
    }
    conf = conf_verify(v["receipt"], mode=v.get("verifier_mode", "strict"), prior_receipts=priors)
    lib = _verify_vector(v, _chain_priors())
    assert lib.ok == conf.ok, (
        f"{v['id']}: lib ok={lib.ok} ({lib.stage}) but conformance ok={conf.ok}"
    )
