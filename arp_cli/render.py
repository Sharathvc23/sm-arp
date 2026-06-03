"""Human-facing renderer for ARP receipts.

The Agency Log view from spec §10.1 — what the principal sees in their
diary app. Drops DIDs, UUIDs, hashes, and signatures by default; the
guarantees those provide live *behind* the rendering, not *in* it.

Authority links are surfaced in plain English ("under authority you
granted at 12:00 PM"), so the diary stays readable even when an action
is two or three delegation hops removed from the human principal.
"""

from __future__ import annotations

from datetime import datetime, timezone


_OUTCOME_GLYPH = {
    "completed": "✓",
    "failed":    "✗",
    "partial":   "◐",
    "reversed":  "↺",
    "pending":   "⋯",
}

_CATEGORY_VERB = {
    "purchase":            "bought",
    "payment_sent":        "sent payment",
    "payment_received":    "received payment",
    "message_sent":        "sent a message",
    "message_received":    "received a message",
    "decision_made":       "made a decision",
    "data_shared":         "shared data",
    "appointment_booked":  "booked an appointment",
    "appointment_cancelled": "cancelled an appointment",
    "record_filed":        "filed a record",
    "vote_cast":           "cast a vote",
    "authority_granted":   "granted authority",
    "authority_revoked":   "revoked authority",
}


# ── formatters ─────────────────────────────────────────────────────


def _format_timestamp(iso: str) -> str:
    """2026-06-03T12:30:00Z → 'Wed Jun 3, 2026 — 12:30 PM UTC'."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return iso
    # Use platform-independent day-of-month (no leading zero)
    return dt.strftime("%a %b ") + str(dt.day) + ", " + dt.strftime("%Y — ") + dt.strftime("%I:%M %p UTC").lstrip("0")


def _format_amount(amount: dict) -> str:
    cents = amount.get("cents", 0)
    currency = amount.get("currency", "")
    sign = "-" if cents < 0 else "+"
    return f"{sign}{currency} {abs(cents)/100:,.2f}"


def _format_jurisdiction(j: dict) -> str:
    """Render the jurisdiction block as a single line of plain prose."""
    parts: list[str] = []
    if "principal_residence" in j:
        parts.append(f"resident of {j['principal_residence']}")
    if "action_locus" in j and j.get("action_locus") != j.get("principal_residence"):
        parts.append(f"acted in {j['action_locus']}")
    regimes = j.get("applicable_regimes")
    if regimes:
        parts.append(", ".join(r.upper() for r in regimes) + " applies")
    return "; ".join(parts)


def _short_did(did: str) -> str:
    """Truncate a did:key for the (rare) cases we have to surface one."""
    if did.startswith("did:key:z"):
        body = did[len("did:key:z"):]
        return f"did:key:z{body[:8]}…"
    return did[:20] + "…"


def _summary(receipt: dict) -> str:
    """Pull the human_summary, falling back to a verb-based reconstruction if absent."""
    s = receipt.get("action", {}).get("human_summary")
    if s:
        return s
    cat = receipt.get("action", {}).get("category", "did something")
    return _CATEGORY_VERB.get(cat, cat).capitalize() + "."


# ── public API ─────────────────────────────────────────────────────


def render_receipt(receipt: dict, *, show_crypto: bool = False, indent: str = "") -> str:
    """Render a single receipt as a diary entry."""
    action = receipt.get("action", {})
    outcome = action.get("outcome", "completed")
    glyph = _OUTCOME_GLYPH.get(outcome, "·")

    lines: list[str] = []
    lines.append(f"{indent}{_format_timestamp(receipt.get('issued_at', '?'))}")
    lines.append(f"{indent}  {glyph} {_summary(receipt)}")

    inner = f"{indent}    "
    if "counterparty_label" in action:
        lines.append(f"{inner}with: {action['counterparty_label']}")
    if "amount" in action:
        lines.append(f"{inner}amount: {_format_amount(action['amount'])}")
    if "jurisdiction" in receipt:
        j = _format_jurisdiction(receipt["jurisdiction"])
        if j:
            lines.append(f"{inner}{j}")
    if receipt.get("accessibility", {}).get("requires_review"):
        lines.append(f"{inner}⚠ flagged for your review")

    # Author transparency: if the issuer differs from the principal, say so.
    issuer = receipt.get("issuer_did", "")
    principal = receipt.get("principal_did", "")
    if issuer and principal and issuer != principal:
        lines.append(f"{inner}taken by an agent on your behalf")
    elif issuer and principal and issuer == principal and action.get("category") in {"authority_granted", "authority_revoked"}:
        lines.append(f"{inner}taken by you (the principal)")

    if show_crypto:
        lines.append("")
        lines.append(f"{inner}receipt_id:  {receipt.get('receipt_id', '?')}")
        lines.append(f"{inner}issuer:      {receipt.get('issuer_did', '?')}")
        lines.append(f"{inner}principal:   {receipt.get('principal_did', '?')}")
        if "previous_receipt_hash" in receipt:
            lines.append(f"{inner}prev_hash:   {receipt['previous_receipt_hash']}")
        if "authority_chain" in receipt:
            lines.append(f"{inner}auth_chain:  {receipt['authority_chain']}")
        sig = receipt.get("signature", "")
        if sig:
            lines.append(f"{inner}signature:   {sig[:32]}… (Ed25519)")

    return "\n".join(lines)


def render_trace(trace: list[dict], *, show_crypto: bool = False) -> str:
    """Render a chronological trace, surfacing authority links inline.

    Receipts are sorted by issued_at. For each receipt that declares
    action.granted_by_receipt_id, the renderer locates the parent grant
    inside the trace and inserts a "under authority granted at X" line
    so the human can see the delegation lineage without UUIDs.
    """
    sorted_trace = sorted(trace, key=lambda r: r.get("issued_at", ""))
    by_id = {r.get("receipt_id"): r for r in sorted_trace}

    blocks: list[str] = []
    for r in sorted_trace:
        block = render_receipt(r, show_crypto=show_crypto)
        gid = r.get("action", {}).get("granted_by_receipt_id")
        if gid and gid in by_id:
            parent = by_id[gid]
            parent_when = _format_timestamp(parent.get("issued_at", "?"))
            parent_summary = _summary(parent)
            if len(parent_summary) > 70:
                parent_summary = parent_summary[:67] + "…"
            block += f'\n      ↳ under authority granted at {parent_when}:\n         "{parent_summary}"'
        blocks.append(block)

    return "\n\n".join(blocks)
