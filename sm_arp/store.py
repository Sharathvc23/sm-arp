"""SQLite-backed receipt log.

The **Issuer Log** (spec §10.2) and the **Agency Log** (§10.1) share one table
shape and one query surface, but differ in what they can know about a chain:

* An **Issuer Log** is an issuer's own audit store. It sees every receipt the
  issuer emits, in order, so each new receipt's ``previous_receipt_hash`` can be
  checked against the issuer's current head (§6.3 step 7: the prior "MUST be
  discoverable in the issuer log"). :class:`IssuerLog` enforces that.
* An **Agency Log** is a principal's store of receipts *about them*, often from
  several issuers, and holds only part of each issuer's chain. Receipts may
  arrive out of order. It cannot check a receipt against a head it never saw.

Both refuse to rewrite or fork what they hold: :meth:`ReceiptLog.append` never
replaces an issuer-signed receipt with different content, and never stores two
receipts by one issuer that claim the same predecessor. A refused append raises
:class:`AppendRefused` and leaves the log unchanged.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar

from .receipts import chain_link

_CHAIN_LINK_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class AppendRefused(ValueError):
    """:meth:`ReceiptLog.append` refused a receipt. ``reason`` is one of:

    * ``"malformed"``: a field the log keys or chains on is missing or the wrong
      type, or ``previous_receipt_hash`` is present but not ``sha256:<64 hex>``;
    * ``"rewrite"``: the log already holds a receipt with this
      ``(issuer_did, receipt_id)`` and different issuer-signed content, or the
      re-append would drop witness co-signatures the log already holds;
    * ``"fork"``: the log already holds a receipt by this issuer that claims the
      same ``previous_receipt_hash``;
    * ``"discontinuity"`` (:class:`IssuerLog` only): ``previous_receipt_hash``
      is not the link of the issuer's current head, or a receipt without one
      would start a second chain for an issuer that already keeps one.
    """

    REASONS: ClassVar[tuple[str, ...]] = ("malformed", "rewrite", "fork", "discontinuity")

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _witnesses(receipt: dict[str, Any]) -> list[Any]:
    evidence = receipt.get("evidence")
    found = evidence.get("witness_signatures") if isinstance(evidence, dict) else None
    return found if isinstance(found, list) else []


class ReceiptLog:
    #: When true, ``append`` also requires each receipt to extend the issuer's
    #: current head. :class:`IssuerLog` sets it. A plain :class:`ReceiptLog` /
    #: :class:`AgencyLog` holds partial chains and does not.
    require_contiguous_chain: ClassVar[bool] = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id   TEXT NOT NULL,
                    issuer_did   TEXT NOT NULL,
                    principal_did TEXT NOT NULL,
                    issued_at    TEXT NOT NULL,
                    category     TEXT,
                    counterparty_did TEXT,
                    previous_receipt_hash TEXT,
                    chain_link   TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    PRIMARY KEY (issuer_did, receipt_id)
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_principal ON receipts(principal_did, issued_at)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_issuer ON receipts(issuer_did, issued_at)")
            # Chain lookups made on every append: successor-of (fork) and link-of (head).
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_issuer_prev "
                "ON receipts(issuer_did, previous_receipt_hash)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_issuer_link ON receipts(issuer_did, chain_link)"
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One write transaction that takes SQLite's write lock *before* reading,
        so the rewrite/fork/head checks and the insert cannot interleave with a
        concurrent append."""
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def append(self, receipt: dict[str, Any]) -> str:
        """Persist a signed receipt and return the chain link it produces.

        Re-appending a receipt the log already holds is a no-op. If the copy being
        appended carries extra witness co-signatures (detached evidence, spec §5.1),
        the stored copy is updated to include them. Anything else that would
        change what the log holds raises :class:`AppendRefused`. See that class
        for the reasons. The log is unchanged after a refusal.

        This method does not verify the receipt's signature. Verify before
        appending (:func:`sm_arp.verify_receipt`).
        """
        if not isinstance(receipt, dict):
            raise AppendRefused("malformed", "receipt is not an object")
        fields: dict[str, str] = {}
        for name in ("receipt_id", "issuer_did", "principal_did", "issued_at"):
            value = receipt.get(name)
            if not isinstance(value, str) or not value:
                raise AppendRefused("malformed", f"{name} is not a non-empty string")
            fields[name] = value
        prev: str | None = None
        if "previous_receipt_hash" in receipt:
            declared = receipt["previous_receipt_hash"]
            if not isinstance(declared, str) or not _CHAIN_LINK_RE.fullmatch(declared):
                raise AppendRefused(
                    "malformed", "previous_receipt_hash is present but not sha256:<64 hex>"
                )
            prev = declared
        issuer, rid = fields["issuer_did"], fields["receipt_id"]
        action = receipt.get("action")
        action = action if isinstance(action, dict) else {}
        link = chain_link(receipt)
        body = json.dumps(receipt, separators=(",", ":"))

        with self._write() as c:
            row = c.execute(
                "SELECT receipt_json FROM receipts WHERE issuer_did = ? AND receipt_id = ?",
                (issuer, rid),
            ).fetchone()
            if row is not None:
                stored = json.loads(row["receipt_json"])
                if chain_link(stored) != link:
                    raise AppendRefused(
                        "rewrite",
                        f"log already holds {rid} from this issuer with different signed content",
                    )
                if stored != receipt:
                    held = _witnesses(receipt)
                    if any(w not in held for w in _witnesses(stored)):
                        raise AppendRefused(
                            "rewrite", f"re-append of {rid} would drop witness co-signatures"
                        )
                    c.execute(
                        "UPDATE receipts SET receipt_json = ?, chain_link = ? "
                        "WHERE issuer_did = ? AND receipt_id = ?",
                        (body, link, issuer, rid),
                    )
                return link

            if prev is not None:
                sibling = c.execute(
                    "SELECT receipt_id FROM receipts "
                    "WHERE issuer_did = ? AND previous_receipt_hash = ? LIMIT 1",
                    (issuer, prev),
                ).fetchone()
                if sibling is not None:
                    raise AppendRefused(
                        "fork",
                        f"{sibling['receipt_id']} by this issuer already claims "
                        f"previous_receipt_hash {prev}",
                    )
            if self.require_contiguous_chain:
                self._check_extends_head(c, issuer, prev)

            c.execute(
                "INSERT INTO receipts (receipt_id, issuer_did, principal_did, "
                "issued_at, category, counterparty_did, previous_receipt_hash, chain_link, "
                "receipt_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rid,
                    issuer,
                    fields["principal_did"],
                    fields["issued_at"],
                    _text(action.get("category")),
                    _text(action.get("counterparty_did")),
                    prev,
                    link,
                    body,
                ),
            )
        return link

    @staticmethod
    def _check_extends_head(c: sqlite3.Connection, issuer: str, prev: str | None) -> None:
        """The new receipt must extend this issuer's chain at its head (§6.3 step 7, §6.4).

        Runs after the fork check, so a predecessor found here has no successor yet.
        """
        chained = (
            c.execute(
                "SELECT 1 FROM receipts "
                "WHERE issuer_did = ? AND previous_receipt_hash IS NOT NULL LIMIT 1",
                (issuer,),
            ).fetchone()
            is not None
        )
        if prev is None:
            if chained:
                raise AppendRefused(
                    "discontinuity",
                    "issuer already keeps a hash chain in this log; a receipt without "
                    "previous_receipt_hash would start a second one",
                )
            return
        pred = c.execute(
            "SELECT previous_receipt_hash FROM receipts "
            "WHERE issuer_did = ? AND chain_link = ? LIMIT 1",
            (issuer, prev),
        ).fetchone()
        if pred is None:
            raise AppendRefused(
                "discontinuity",
                f"previous_receipt_hash {prev} is not the link of any receipt by this "
                "issuer in the log",
            )
        if pred["previous_receipt_hash"] is None and chained:
            # The chain's own genesis already has a successor (the fork check would
            # have fired), so this is a different genesis-shaped receipt: linking to it
            # would start a second chain beside the existing head.
            raise AppendRefused(
                "discontinuity",
                f"previous_receipt_hash {prev} is not the head of this issuer's chain",
            )

    def _q(self, where: str, args: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                f"SELECT receipt_json FROM receipts {where} ORDER BY issued_at DESC LIMIT ?",
                (*args, limit),
            ).fetchall()
        return [json.loads(r["receipt_json"]) for r in rows]

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._q("", (), limit)

    def list_for_principal(self, principal_did: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._q("WHERE principal_did = ?", (principal_did,), limit)

    def list_for_issuer(self, issuer_did: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._q("WHERE issuer_did = ?", (issuer_did,), limit)

    def get(self, receipt_id: str, issuer_did: str | None = None) -> dict[str, Any] | None:
        where = "WHERE receipt_id = ?" + (" AND issuer_did = ?" if issuer_did else "")
        args = (receipt_id, issuer_did) if issuer_did else (receipt_id,)
        rows = self._q(where, args, 1)
        return rows[0] if rows else None

    def count(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])


class IssuerLog(ReceiptLog):
    """An issuer's own audit log (§10.2). It holds the issuer's whole chain in
    issuance order, so on top of :class:`ReceiptLog`'s rewrite and fork refusals,
    ``append`` requires each receipt to extend the issuer's current head:

    * a receipt with ``previous_receipt_hash`` must link to a receipt by the same
      issuer already in this log, and that receipt must be the head. Gaps,
      links into another issuer's chain, and branches off an older receipt are
      refused;
    * a receipt without ``previous_receipt_hash`` (a genesis, or a receipt from an
      issuer that does not chain, §6.4) is refused once the issuer already keeps
      a chain in this log.

    These checks cover receipts appended through this method. Rows written by
    sm-arp releases before this check existed are not re-validated.
    """

    require_contiguous_chain: ClassVar[bool] = True


AgencyLog = ReceiptLog
