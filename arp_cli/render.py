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
from typing import Optional

from conformance.arp import compute_chain_link, verify_receipt


# Minimal ANSI styling — keeps render.py free of typer/click so the
# module can be reused outside the CLI (e.g. a future web Agency Log).
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


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


def _summary(receipt: dict, *, lang: Optional[str] = None) -> str:
    """Pull the human_summary in the requested language, falling back gracefully.

    Resolution order (per spec §9.2):
      1. If ``lang`` requested and accessibility.alt_summaries has an exact
         match (e.g. "ja-JP"), return that summary.
      2. If ``lang`` requested as a prefix (e.g. "es") matches the prefix of
         an alt entry (e.g. "es-MX"), return that.
      3. Fall back to the primary action.human_summary.
      4. If absent entirely, reconstruct a verb-based stub from the category.
    """
    action = receipt.get("action", {})
    primary = action.get("human_summary")

    if lang:
        alts = receipt.get("accessibility", {}).get("alt_summaries", []) or []
        for alt in alts:
            if alt.get("lang", "").lower() == lang.lower():
                return alt.get("summary", "") or primary or ""
        prefix = lang.split("-")[0].lower()
        for alt in alts:
            if alt.get("lang", "").split("-")[0].lower() == prefix:
                return alt.get("summary", "") or primary or ""

    if primary:
        return primary
    cat = action.get("category", "did something")
    return _CATEGORY_VERB.get(cat, cat).capitalize() + "."


def _verify_status(
    receipt: dict,
    *,
    priors: Optional[dict[str, dict]] = None,
) -> tuple[str, str, str]:
    """Verify the receipt and classify the outcome for the human-facing view.

    Returns ``(label, color, detail)`` where ``label`` is one of:
      - "VERIFIED"          — schema + Ed25519 (and any chain link) all pass
      - "FORGED"            — Ed25519 signature does not cover the body shown
      - "MALFORMED"         — schema validation fails; receipt is structurally invalid
      - "CHAIN UNVERIFIED"  — declares previous_receipt_hash but no prior is on hand
      - "UNVERIFIED"        — anything else (defensive fall-through)
    """
    result = verify_receipt(receipt, mode="strict", prior_receipts=priors)
    if result.ok:
        return ("VERIFIED", _GREEN, "schema + Ed25519 signature OK")
    if result.stage == "signature":
        return ("FORGED", _RED, "Ed25519 signature does not cover the body shown")
    if result.stage == "schema":
        return ("MALFORMED", _RED, f"schema: {result.detail}")
    if result.stage == "hash_chain":
        return ("CHAIN UNVERIFIED", _YELLOW, "previous_receipt_hash claim cannot be resolved without the prior receipt")
    return ("UNVERIFIED", _YELLOW, f"{result.stage}: {result.detail}")


# ── public API ─────────────────────────────────────────────────────


def render_receipt(
    receipt: dict,
    *,
    show_crypto: bool = False,
    priors: Optional[dict[str, dict]] = None,
    lang: Optional[str] = None,
    indent: str = "",
) -> str:
    """Render a single receipt as a diary entry.

    Always verifies first (spec §4.1 — human-readable + machine-verifiable).
    A FORGED or MALFORMED receipt is rendered with a prominent warning
    rather than a misleading green ✓; the body is still shown for reference
    so the human can see what was claimed, but they're told not to rely on it.

    ``priors`` is an optional ``previous_receipt_hash → prior receipt`` map
    so hash-chain links can resolve when supplied (typically built from a
    trace and threaded through by ``render_trace``).

    ``lang`` (BCP 47) selects an alt_summaries entry when present.
    """
    action = receipt.get("action", {})
    outcome = action.get("outcome", "completed")
    glyph = _OUTCOME_GLYPH.get(outcome, "·")

    status_label, status_color, status_detail = _verify_status(receipt, priors=priors)
    status_pill = f"{status_color}{_BOLD}{status_label}{_RESET}"

    lines: list[str] = []
    ts = _format_timestamp(receipt.get("issued_at", "?"))
    lines.append(f"{indent}{ts}  {status_pill}")

    if status_label in {"FORGED", "MALFORMED"}:
        # Use "?" not the outcome glyph: a green ✓ next to a FORGED body
        # would imply success, contradicting the status pill above.
        lines.append(f"{indent}  {_RED}?{_RESET} {_summary(receipt, lang=lang)}")
        lines.append(f"{indent}    {_RED}⚠ {status_detail}{_RESET}")
        lines.append(f"{indent}    {_RED}Body shown for reference; do not rely on these contents.{_RESET}")
    else:
        lines.append(f"{indent}  {glyph} {_summary(receipt, lang=lang)}")
        if status_label != "VERIFIED":
            lines.append(f"{indent}    {_YELLOW}⚠ {status_detail}{_RESET}")

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


def render_trace(
    trace: list[dict],
    *,
    show_crypto: bool = False,
    lang: Optional[str] = None,
) -> str:
    """Render a chronological trace, surfacing both edge types inline.

    Receipts are sorted by issued_at. Two relationship types get plain-prose
    annotations so the human can see the lineage without UUIDs:

      - ``action.granted_by_receipt_id`` → "under authority granted at X"
        (cross-principal delegation chain, spec §4.5/4.6)
      - ``previous_receipt_hash``        → "follows tamper-chain from X"
        (per-issuer time-ordered chain, spec §6.4)

    Each receipt is verified with the in-trace priors map threaded in, so
    previous_receipt_hash claims resolve when the prior is present.
    """
    sorted_trace = sorted(trace, key=lambda r: r.get("issued_at", ""))
    by_id = {r.get("receipt_id"): r for r in sorted_trace}
    by_chain_link = {compute_chain_link(r): r for r in sorted_trace}

    blocks: list[str] = []
    for r in sorted_trace:
        block = render_receipt(r, show_crypto=show_crypto, priors=by_chain_link, lang=lang)

        gid = r.get("action", {}).get("granted_by_receipt_id")
        if gid and gid in by_id:
            parent = by_id[gid]
            parent_when = _format_timestamp(parent.get("issued_at", "?"))
            parent_summary = _summary(parent, lang=lang)
            if len(parent_summary) > 70:
                parent_summary = parent_summary[:67] + "…"
            block += f'\n      ↳ under authority granted at {parent_when}:\n         "{parent_summary}"'

        prev_hash = r.get("previous_receipt_hash")
        if prev_hash and prev_hash in by_chain_link:
            prior = by_chain_link[prev_hash]
            prior_when = _format_timestamp(prior.get("issued_at", "?"))
            prior_summary = _summary(prior, lang=lang)
            if len(prior_summary) > 70:
                prior_summary = prior_summary[:67] + "…"
            block += f'\n      ↳ follows tamper-chain from earlier receipt at {prior_when}:\n         "{prior_summary}"'

        blocks.append(block)

    return "\n\n".join(blocks)
