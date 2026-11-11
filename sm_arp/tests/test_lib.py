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
    canonical_bytes,
    chain_link,
    detach_witnesses,
    issue_receipt,
    verify_authority_chain,
    verify_hash_chain,
    verify_receipt,
)
from sm_arp.vrp import cosign_receipt, is_corroborated

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
            machine_payload={
                "granted_to_did": agent.did,
                "granted_scope": ["data_shared"],
                "grant_expires_at": "2099-01-01T00:00:00Z",
            },
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


# ── audit 2026-11: detached witness evidence (spec §5, §6.1, §6.4) ──────────


def _grant_and_action(
    *,
    payload_overrides: dict[str, Any] | None = None,
    grant_issued_at: str | None = None,
    action_issued_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    grantor, agent = Identity.generate(), Identity.generate()
    payload: dict[str, Any] = {
        "granted_to_did": agent.did,
        "granted_scope": ["data_shared"],
        "grant_expires_at": "2099-01-01T00:00:00Z",
    }
    payload.update(payload_overrides or {})
    payload = {k: v for k, v in payload.items() if v is not None}
    grant = issue_receipt(
        grantor,
        principal_did=grantor.did,
        issued_at=grant_issued_at,
        action=build_action(
            category="authority_granted", human_summary="granted", machine_payload=payload
        ),
    )
    action = issue_receipt(
        agent,
        principal_did=grantor.did,
        issued_at=action_issued_at,
        action=_action(category="data_shared", granted_by_receipt_id=grant["receipt_id"]),
    )
    return grant, action


def test_witness_appended_after_issuance_keeps_issuer_signature_and_chain_link() -> None:
    """The audit's headline finding: appending a witness to an already-signed receipt
    used to invalidate the issuer signature (and move the chain link), because the
    issuer signature covered ``evidence.witness_signatures``. Witnesses are detached
    evidence (§5): a signature a third party appends cannot be inside the bytes the
    issuer signed, and a successor that already committed to the predecessor's link
    must keep linking after the predecessor gains a witness."""
    issuer, counterparty = Identity.generate(), Identity.generate()
    r1 = issue_receipt(
        issuer,
        principal_did=issuer.did,
        action=_action(category="purchase", counterparty_did=counterparty.did),
        evidence={"external_refs": ["ORDER-1"]},
    )
    r2 = issue_receipt(
        issuer, principal_did=issuer.did, action=_action(), previous_receipt_hash=chain_link(r1)
    )
    link_before = chain_link(r1)
    signed_bytes_before = canonical_bytes(r1, include_signature=False)

    # A witness lands after issuance — spec-keyed, then alias-keyed (sm-oversight).
    entry = cosign_receipt(r1, signing_key_bytes=counterparty.sk_bytes)
    r1["evidence"]["witness_signatures"] = [entry]
    r1["evidence"]["witness_signatures"].append(
        {"signer_did": Identity.generate().did, "signature": entry["signature"]}
    )

    assert verify_receipt(r1).ok, "issuer signature must survive a detached witness"
    assert chain_link(r1) == link_before, "chain link must not move when a witness lands"
    assert verify_hash_chain(r2, r1).ok
    assert canonical_bytes(r1, include_signature=False) == signed_bytes_before
    assert is_corroborated(r1)
    # The witness list stays on the receipt object; only the byte commitments
    # detach it, and detaching never mutates the input.
    assert "witness_signatures" not in detach_witnesses(r1)["evidence"]
    assert "witness_signatures" in r1["evidence"]


def test_witness_only_evidence_detaches_to_no_evidence() -> None:
    """A receipt whose ``evidence`` carries only witnesses canonicalises exactly like
    one issued with no ``evidence`` at all — so an issuer that signed without evidence
    still verifies after a witness creates the object."""
    issuer = Identity.generate()
    r = issue_receipt(issuer, principal_did=issuer.did, action=_action())
    bare = canonical_bytes(r, include_signature=False)
    r["evidence"] = {"witness_signatures": [{"witness_did": issuer.did, "signature": "AA=="}]}
    assert canonical_bytes(r, include_signature=False) == bare
    assert "evidence" not in detach_witnesses(r)
    assert verify_receipt(r).ok


@pytest.mark.parametrize("path", _VECTOR_PATHS, ids=lambda p: p.stem)
def test_detached_rule_is_a_no_op_on_witnessless_receipts(path: Path) -> None:
    """Every pre-existing vector has no witnesses, so the detached rule must leave its
    signed bytes and chain link exactly as before the rule existed — the corpus
    signatures were NOT regenerated, and this is why they did not need to be."""
    import jcs

    r = _load(path)["receipt"]
    if "witness_signatures" in (r.get("evidence") or {}):
        pytest.skip("witnessed vector — covered by the vector's own verdict")
    body = {k: v for k, v in r.items() if k != "signature"}
    assert canonical_bytes(r, include_signature=False) == jcs.canonicalize(body)
    assert canonical_bytes(r, include_signature=True) == jcs.canonicalize(r)


def test_witnessed_vectors_verify_and_only_the_intact_one_corroborates() -> None:
    """Vector 23: witnesses appended after issuance, issuer signature intact,
    counterparty corroborates. Vector 24: the counterparty's co-signature was
    tampered — the issuer signature is untouched (witnesses are outside it) but
    corroboration is gone. Tampering a witness breaks only that witness."""
    v23 = _load(_VECTORS_DIR / "23-witnessed-receipt.json")["receipt"]
    v24 = _load(_VECTORS_DIR / "24-witness-tampered.json")["receipt"]
    assert verify_receipt(v23).ok
    assert verify_receipt(v24).ok
    assert is_corroborated(v23) is True
    assert is_corroborated(v24) is False
    # The chain link detaches witnesses: stripping them changes nothing (§6.4).
    for v in (v23, v24):
        stripped = {**v, "evidence": {"external_refs": v["evidence"]["external_refs"]}}
        assert chain_link(v) == chain_link(stripped)
        assert canonical_bytes(v, include_signature=True) == canonical_bytes(
            stripped, include_signature=True
        )


# ── audit 2026-11: strict structure, verifier modes ─────────────────────────


def test_unknown_top_level_member_strict_rejects_tolerant_accepts() -> None:
    """Spec §3: unknown top-level members MUST be rejected by a strict verifier and
    MAY be preserved by a tolerant one. The rejection is structural (it mirrors the
    schema's additionalProperties: false) and fires before the signature stage."""
    issuer = Identity.generate()
    r = issue_receipt(issuer, principal_did=issuer.did, action=_action())
    r["workflow_id"] = "WF-1"  # not signed over → tolerant falls through to signature
    res = verify_receipt(r, mode="strict")
    assert not res.ok and res.stage == "structure" and "workflow_id" in res.detail
    assert verify_receipt(r, mode="tolerant").stage == "signature"
    # Vector 25 signed over the unknown member: strict still rejects, tolerant accepts.
    v25 = _load(_VECTORS_DIR / "25-unknown-top-level-member.json")["receipt"]
    assert verify_receipt(v25, mode="strict").stage == "structure"
    assert verify_receipt(v25, mode="tolerant").ok


def test_extensions_are_the_sanctioned_carrier_not_unknown_members() -> None:
    issuer = Identity.generate()
    r = issue_receipt(
        issuer, principal_did=issuer.did, action=_action(), composition={"x": 1}
    )  # `composition` is not a §3.2 member either
    assert verify_receipt(r, mode="strict").stage == "structure"
    r = issue_receipt(issuer, principal_did=issuer.did, action=_action())
    r["extensions"] = {"acme.example.workflow-id": "WF-1"}
    assert verify_receipt(r, mode="strict").stage == "signature"  # structure accepted


@pytest.mark.parametrize("mode", ["Strict", "lenient", "", "permissive"])
def test_unknown_verifier_mode_raises_instead_of_degrading_to_tolerant(mode: str) -> None:
    """Any string other than "strict" used to silently select tolerant verification —
    a typo in a caller's config weakened verification without a trace."""
    issuer = Identity.generate()
    r = issue_receipt(issuer, principal_did=issuer.did, action=_action())
    with pytest.raises(ValueError, match="unknown verifier mode"):
        verify_receipt(r, mode=mode)
    assert verify_receipt(r, mode="tolerant").ok and verify_receipt(r, mode="strict").ok


# ── audit 2026-11: verify_authority_chain authenticates the grant ───────────


def test_authority_chain_happy_path_still_verifies() -> None:
    grant, action = _grant_and_action()
    assert verify_authority_chain(action, {grant["receipt_id"]: grant}).ok
    assert verify_receipt(action, grants={grant["receipt_id"]: grant}).ok


def test_authority_chain_rejects_forged_grant_signature() -> None:
    """The grant index is caller-supplied; a grant that does not verify under its own
    issuer_did authorises nothing, however well its fields line up."""
    grant, action = _grant_and_action()
    forged = dict(grant)
    forged["action"] = dict(grant["action"], human_summary="rewritten")
    res = verify_authority_chain(action, {grant["receipt_id"]: forged})
    assert not res.ok and res.stage == "authority_chain" and "signature" in res.detail
    unsigned = {k: v for k, v in grant.items() if k != "signature"}
    res = verify_authority_chain(action, {grant["receipt_id"]: unsigned})
    assert not res.ok and res.stage == "authority_chain"


def test_authority_chain_rejects_index_key_that_is_not_the_grant_receipt_id() -> None:
    grant, action = _grant_and_action()
    other, _ = _grant_and_action()
    res = verify_authority_chain(action, {grant["receipt_id"]: other})
    assert not res.ok and "does not match grant receipt_id" in res.detail


@pytest.mark.parametrize("granted_to", [None, "", "did:key:z6MkSomebodyElse"])
def test_authority_chain_requires_grantee_to_be_the_issuer(granted_to: str | None) -> None:
    """An absent grantee used to be admitted ("anyone"); the grant must name the agent."""
    grant, action = _grant_and_action(payload_overrides={"granted_to_did": granted_to})
    res = verify_authority_chain(action, {grant["receipt_id"]: grant})
    assert not res.ok and res.stage == "authority_chain"
    assert "granted_to_did" in res.detail or "grantee" in res.detail


@pytest.mark.parametrize(
    "expires",
    [None, "", "never", "2099-01-01", "2099-01-01T00:00:00", "2000-01-01T00:00:00Z"],
    ids=["absent", "empty", "word", "date-only", "naive", "expired"],
)
def test_authority_chain_requires_a_parseable_future_expiry(expires: str | None) -> None:
    """Empty/absent expiry used to mean "never expires", and expiry was compared as a
    string. Now it must parse as an aware RFC 3339 instant later than issued_at."""
    grant, action = _grant_and_action(payload_overrides={"grant_expires_at": expires})
    res = verify_authority_chain(action, {grant["receipt_id"]: grant})
    assert not res.ok and res.stage == "authority_chain", res


def test_authority_chain_compares_expiry_as_instants_not_strings() -> None:
    """``2030-01-01T01:00:00+01:00`` IS ``2030-01-01T00:00:00Z``. As a string it sorts
    after an action issued at ``00:30:00Z`` (so the old code called the grant live);
    as an instant it is half an hour before it (expired)."""
    expiry, issued = "2030-01-01T01:00:00+01:00", "2030-01-01T00:30:00Z"
    assert expiry > issued  # the string comparison the old code relied on
    grant, action = _grant_and_action(
        payload_overrides={"grant_expires_at": expiry},
        grant_issued_at="2029-12-31T00:00:00Z",
        action_issued_at=issued,
    )
    res = verify_authority_chain(action, {grant["receipt_id"]: grant})
    assert not res.ok and "expired" in res.detail
    grant, action = _grant_and_action(
        payload_overrides={"grant_expires_at": expiry},
        grant_issued_at="2029-12-31T00:00:00Z",
        action_issued_at="2029-12-31T23:59:59Z",
    )
    assert verify_authority_chain(action, {grant["receipt_id"]: grant}).ok


def test_authority_chain_does_not_order_grant_against_action() -> None:
    """Deliberately NOT checked here: a grant receipt issued after the action. The
    grant index path is used with wall-clock-issued grant receipts wrapping DATs that
    carry their own validity window (sm-dat's bridge); grant/action ordering is
    enforced by ``verify_direct_grant`` (``start <= issued``), which owns that model."""
    grant, action = _grant_and_action(
        grant_issued_at="2030-01-01T00:00:01Z", action_issued_at="2030-01-01T00:00:00Z"
    )
    assert verify_authority_chain(action, {grant["receipt_id"]: grant}).ok


@pytest.mark.parametrize("scope", [None, [], "data_shared"], ids=["absent", "empty", "string"])
def test_authority_chain_requires_a_non_empty_scope_list(scope: object) -> None:
    grant, action = _grant_and_action(payload_overrides={"granted_scope": scope})
    res = verify_authority_chain(action, {grant["receipt_id"]: grant})
    assert not res.ok and res.stage == "authority_chain"


def test_authority_chain_rejects_malformed_grant_objects_without_raising() -> None:
    _, action = _grant_and_action()
    gid = action["action"]["granted_by_receipt_id"]
    for bad in ("not-a-dict", {"receipt_id": gid}, {"receipt_id": gid, "action": "x"}):
        res = verify_authority_chain(action, {gid: cast(dict[str, Any], bad)})
        assert not res.ok and res.stage == "authority_chain"
