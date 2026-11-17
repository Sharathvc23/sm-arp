"""Receipt log append semantics: no rewrites, no forks, and (Issuer Log) no gaps.

REWRITE        same (issuer_did, receipt_id), different signed content → refused
WITNESSES      a re-append may add detached witness co-signatures, never drop them
FORK           two receipts by one issuer claiming one predecessor → refused (all logs)
HEAD           IssuerLog: each receipt extends the issuer's current head
PARTIAL VIEW   AgencyLog: partial / out-of-order chains are accepted
MALFORMED      hostile field types are refused, not stored or crashed on
ATOMIC         a refusal leaves the log unchanged; concurrent forks admit one
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from sm_arp import (
    AgencyLog,
    AppendRefused,
    Identity,
    IssuerLog,
    ReceiptLog,
    build_action,
    chain_link,
    issue_receipt,
)
from sm_arp.vrp import cosign_receipt


def _r(issuer: Identity, prev: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    summary = kw.pop("summary", "Voted yes.")
    return issue_receipt(
        issuer,
        principal_did=kw.pop("principal_did", issuer.did),
        action=build_action(category="vote_cast", human_summary=summary),
        previous_receipt_hash=chain_link(prev) if prev is not None else None,
        **kw,
    )


def _cosigned(receipt: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``receipt`` with one more witness co-signature appended (§5.1)."""
    out: dict[str, Any] = json.loads(json.dumps(receipt))
    entry = cosign_receipt(out, signing_key_bytes=Identity.generate().sk_bytes)
    out.setdefault("evidence", {}).setdefault("witness_signatures", []).append(entry)
    return out


def _refused(log: ReceiptLog, receipt: Any, reason: str) -> AppendRefused:
    before = log.count()
    with pytest.raises(AppendRefused) as exc:
        log.append(receipt)
    assert exc.value.reason == reason, exc.value
    assert log.count() == before
    return exc.value


@pytest.fixture
def issuer() -> Identity:
    return Identity.generate()


@pytest.fixture(params=[IssuerLog, AgencyLog], ids=["issuer_log", "agency_log"])
def log(request: pytest.FixtureRequest, tmp_path: Path) -> ReceiptLog:
    cls: type[ReceiptLog] = request.param
    return cls(tmp_path / "log.sqlite")


def test_log_classes() -> None:
    assert issubclass(IssuerLog, ReceiptLog) and IssuerLog.require_contiguous_chain
    assert AgencyLog is ReceiptLog and not AgencyLog.require_contiguous_chain
    assert issubclass(AppendRefused, ValueError)


# ── rewrites ─────────────────────────────────────────────────────────


def test_identical_reappend_is_a_noop(log: ReceiptLog, issuer: Identity) -> None:
    g = _r(issuer)
    a = _r(issuer, g)
    assert log.append(g) == chain_link(g)
    assert log.append(a) == chain_link(a)
    # Re-appending the genesis after the head moved on is still a no-op, not a
    # second genesis (sm-org-agent re-syncs this way).
    assert log.append(g) == chain_link(g)
    assert log.count() == 2


def test_rewrite_with_same_receipt_id_is_refused(log: ReceiptLog, issuer: Identity) -> None:
    g = _r(issuer)
    log.append(g)
    rewritten = _r(issuer, receipt_id=g["receipt_id"], summary="Voted no.")
    err = _refused(log, rewritten, "rewrite")
    assert g["receipt_id"] in str(err)
    assert log.get(g["receipt_id"]) == g


def test_tampered_copy_of_a_stored_receipt_is_refused(log: ReceiptLog, issuer: Identity) -> None:
    """Same id and signature, body edited after signing: still a rewrite."""
    g = _r(issuer)
    log.append(g)
    tampered = json.loads(json.dumps(g))
    tampered["action"]["human_summary"] = "Voted no."
    _refused(log, tampered, "rewrite")
    assert log.get(g["receipt_id"]) == g


def test_same_receipt_id_from_another_issuer_is_not_a_rewrite(log: ReceiptLog) -> None:
    """§3.3: receipt_id is issuer-scoped."""
    a, b = Identity.generate(), Identity.generate()
    rid = "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a"
    log.append(_r(a, receipt_id=rid))
    log.append(_r(b, receipt_id=rid))
    assert log.count() == 2


def test_reappend_may_add_witnesses_but_not_drop_them(log: ReceiptLog, issuer: Identity) -> None:
    """Witness co-signatures are detached evidence (§5.1): they arrive after
    issuance and leave the chain link unchanged, so the log keeps the newest
    witness set but never loses one it holds."""
    g = _r(issuer)
    log.append(g)
    witnessed = _cosigned(g)
    assert chain_link(witnessed) == chain_link(g)
    assert log.append(witnessed) == chain_link(g)
    assert log.get(g["receipt_id"]) == witnessed
    _refused(log, g, "rewrite")  # the bare copy would drop the co-signature
    twice = _cosigned(witnessed)
    log.append(twice)
    assert log.get(g["receipt_id"]) == twice
    assert log.count() == 1


# ── forks ─────────────────────────────────────────────────────────────


def test_fork_is_refused(log: ReceiptLog, issuer: Identity) -> None:
    g = _r(issuer)
    log.append(g)
    log.append(_r(issuer, g, summary="First successor."))
    err = _refused(log, _r(issuer, g, summary="Second successor."), "fork")
    assert chain_link(g) in str(err)


def test_fork_is_refused_even_when_the_predecessor_is_not_held(tmp_path: Path) -> None:
    """An Agency Log holds partial chains, but two receipts claiming one predecessor
    are a fork whatever else the log holds."""
    issuer = Identity.generate()
    g = _r(issuer)  # never appended
    log = AgencyLog(tmp_path / "agency.sqlite")
    log.append(_r(issuer, g, summary="One."))
    _refused(log, _r(issuer, g, summary="Two."), "fork")


def test_chains_of_different_issuers_are_independent(log: ReceiptLog) -> None:
    a, b = Identity.generate(), Identity.generate()
    ga, gb = _r(a), _r(b)
    for r in (ga, gb, _r(a, ga), _r(b, gb)):
        log.append(r)
    assert log.count() == 4


# ── IssuerLog: the issuer's current head ───────────────────────────────────


def test_issuer_log_accepts_a_linear_chain(tmp_path: Path, issuer: Identity) -> None:
    log = IssuerLog(tmp_path / "issuer.sqlite")
    prev = None
    for i in range(5):
        r = _r(issuer, prev, summary=f"Vote {i}.")
        log.append(r)
        prev = r
    assert log.count() == 5


def test_issuer_log_refuses_a_gap(tmp_path: Path, issuer: Identity) -> None:
    log = IssuerLog(tmp_path / "issuer.sqlite")
    g = _r(issuer)
    log.append(g)
    missing = _r(issuer, g, summary="Never appended.")
    _refused(log, _r(issuer, missing, summary="After the gap."), "discontinuity")


def test_issuer_log_refuses_a_first_receipt_that_links_to_nothing(
    tmp_path: Path, issuer: Identity
) -> None:
    """§6.3 step 7: the prior MUST be discoverable in the issuer log."""
    log = IssuerLog(tmp_path / "issuer.sqlite")
    elsewhere = _r(issuer)
    _refused(log, _r(issuer, elsewhere), "discontinuity")
    forged = _r(issuer)
    forged["previous_receipt_hash"] = "sha256:" + "0" * 64
    _refused(log, forged, "discontinuity")


def test_issuer_log_refuses_a_link_into_another_issuers_chain(tmp_path: Path) -> None:
    log = IssuerLog(tmp_path / "issuer.sqlite")
    a, b = Identity.generate(), Identity.generate()
    ga = _r(a)
    log.append(ga)
    log.append(_r(b))
    _refused(log, _r(b, ga), "discontinuity")


def test_issuer_log_refuses_a_branch_off_an_older_receipt(tmp_path: Path, issuer: Identity) -> None:
    log = IssuerLog(tmp_path / "issuer.sqlite")
    g = _r(issuer)
    a = _r(issuer, g)
    b = _r(issuer, a)
    for r in (g, a, b):
        log.append(r)
    _refused(log, _r(issuer, a, summary="Branch."), "fork")
    _refused(log, _r(issuer, g, summary="Branch."), "fork")


def test_issuer_log_refuses_a_second_genesis_once_chained(tmp_path: Path, issuer: Identity) -> None:
    log = IssuerLog(tmp_path / "issuer.sqlite")
    g = _r(issuer)
    log.append(g)
    log.append(_r(issuer, g))
    _refused(log, _r(issuer, summary="New genesis."), "discontinuity")


def test_issuer_log_accepts_an_issuer_that_does_not_chain(tmp_path: Path, issuer: Identity) -> None:
    """§6.4: issuers that do not maintain chains omit previous_receipt_hash."""
    log = IssuerLog(tmp_path / "issuer.sqlite")
    for i in range(3):
        log.append(_r(issuer, summary=f"Unchained {i}."))
    assert log.count() == 3


def test_issuer_log_chain_started_after_unchained_receipts_is_then_linear(
    tmp_path: Path, issuer: Identity
) -> None:
    """Once an issuer starts chaining off one receipt, linking to any other
    genesis-shaped receipt would be a second chain beside the head."""
    log = IssuerLog(tmp_path / "issuer.sqlite")
    u1, u2 = _r(issuer, summary="U1."), _r(issuer, summary="U2.")
    log.append(u1)
    log.append(u2)
    c1 = _r(issuer, u2, summary="Chained.")
    log.append(c1)
    _refused(log, _r(issuer, u1, summary="Second chain."), "discontinuity")
    log.append(_r(issuer, c1, summary="Extends the head."))
    assert log.count() == 4


# ── AgencyLog: partial, out-of-order views ─────────────────────────────


def test_agency_log_accepts_partial_and_out_of_order_chains(tmp_path: Path) -> None:
    """A principal's log holds only the receipts about them, from many issuers, in
    whatever order they arrive. It cannot check heads it never saw."""
    issuer = Identity.generate()
    principal = Identity.generate()
    g = _r(issuer, principal_did=principal.did)
    a = _r(issuer, g, principal_did="did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK")
    b = _r(issuer, a, principal_did=principal.did)
    log = AgencyLog(tmp_path / "agency.sqlite")
    log.append(b)  # arrives before its (absent) predecessor
    log.append(g)
    assert log.count() == 2


# ── malformed input ─────────────────────────────────────────────────────


def _valid(issuer: Identity) -> dict[str, Any]:
    return _r(issuer)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("receipt_id"),
        lambda r: r.update(receipt_id=["x"]),
        lambda r: r.update(receipt_id=""),
        lambda r: r.update(issuer_did={"did": "x"}),
        lambda r: r.pop("principal_did"),
        lambda r: r.update(issued_at=None),
        lambda r: r.update(previous_receipt_hash=None),
        lambda r: r.update(previous_receipt_hash=""),
        lambda r: r.update(previous_receipt_hash="sha256:XYZ"),
        lambda r: r.update(previous_receipt_hash="sha256:" + "A" * 64),
        lambda r: r.update(previous_receipt_hash=["sha256:" + "0" * 64]),
    ],
    ids=[
        "no-receipt_id",
        "list-receipt_id",
        "empty-receipt_id",
        "dict-issuer_did",
        "no-principal_did",
        "null-issued_at",
        "null-previous_receipt_hash",
        "empty-previous_receipt_hash",
        "short-previous_receipt_hash",
        "uppercase-previous_receipt_hash",
        "list-previous_receipt_hash",
    ],
)
def test_malformed_receipts_are_refused(log: ReceiptLog, issuer: Identity, mutate: Any) -> None:
    r = _valid(issuer)
    mutate(r)
    _refused(log, r, "malformed")


@pytest.mark.parametrize("bad", [None, [], "receipt", 7])
def test_non_object_is_refused(log: ReceiptLog, bad: Any) -> None:
    _refused(log, bad, "malformed")


def test_hostile_indexed_column_types_do_not_crash(log: ReceiptLog, issuer: Identity) -> None:
    """category / counterparty_did are index columns only; a non-string value is
    stored as NULL there (the receipt JSON is kept verbatim)."""
    action = build_action(category="vote_cast", human_summary="Voted.")
    action["category"] = {"nested": True}
    action["counterparty_did"] = ["x"]
    r = issue_receipt(issuer, principal_did=issuer.did, action=action)
    log.append(r)
    assert log.get(r["receipt_id"]) == r


# ── atomicity ───────────────────────────────────────────────────────────


def test_concurrent_forks_admit_exactly_one(tmp_path: Path, issuer: Identity) -> None:
    """The fork check and the insert run in one write transaction, so two appenders
    racing to extend the same predecessor cannot both succeed."""
    path = tmp_path / "issuer.sqlite"
    IssuerLog(path).append(g := _r(issuer))
    forks = [_r(issuer, g, summary=f"Racer {i}.") for i in range(8)]
    barrier = threading.Barrier(len(forks))
    outcomes: list[str] = []
    lock = threading.Lock()

    def run(r: dict[str, Any]) -> None:
        log = IssuerLog(path)
        barrier.wait()
        try:
            log.append(r)
            result = "ok"
        except AppendRefused as e:
            result = e.reason
        except sqlite3.OperationalError as e:  # pragma: no cover - would be a bug
            result = f"sqlite: {e}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run, args=(r,)) for r in forks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["fork"] * (len(forks) - 1) + ["ok"]
    assert IssuerLog(path).count() == 2
