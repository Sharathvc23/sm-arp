"""arp — ARP v0.1 command-line tool (Typer)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import typer

from arp_cli import corpus, issue as _issue, narrate, render as _render
from conformance.arp import compute_chain_link, verify_receipt

app = typer.Typer(
    name="arp",
    help="Agency Receipt Protocol CLI — verify receipts, walk delegation chains, demo the format.",
    add_completion=False,
    no_args_is_help=True,
)
vectors_app = typer.Typer(
    name="vectors",
    help="Operate over the in-repo golden vectors.",
    no_args_is_help=True,
)
app.add_typer(vectors_app, name="vectors")


# ── helpers ────────────────────────────────────────────────────────


def _load(path: Path) -> dict | list:
    """Read JSON or fail with a clean error message."""
    if not path.is_file():
        typer.secho(f"error: {path} is not a file", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        typer.secho(f"error: {path}: invalid JSON: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)


def _verify_one(
    receipt: dict,
    mode: str,
    priors: Optional[dict[str, dict]] = None,
) -> tuple[bool, str, str]:
    """Run verify_receipt and return (ok, stage, detail).

    `priors` is the previous_receipt_hash → prior-receipt map; pass when the
    receipt may declare a previous_receipt_hash and you want the chain check
    to actually resolve. None means "no prior context" (chain step will fail
    for any receipt that declares a hash-chain link, which is the right
    behaviour for verifying a single isolated receipt).
    """
    result = verify_receipt(receipt, mode=mode, prior_receipts=priors)
    return result.ok, result.stage, result.detail


# ── verify ─────────────────────────────────────────────────────────


@app.command()
def verify(
    file: Path = typer.Argument(..., help="Path to a receipt JSON file (or an array of receipts)."),
    mode: str = typer.Option("strict", "--mode", "-m", help="Verifier mode: strict or tolerant."),
) -> None:
    """Verify a single receipt or a trace (array of receipts).

    Runs schema validation, Ed25519 signature check, and (if present) the
    previous_receipt_hash chain check. Auto-detects single vs. trace by
    inspecting the JSON root.
    """
    body = _load(file)
    receipts: list[dict] = body if isinstance(body, list) else [body]

    typer.echo()
    typer.echo(f"verifying {file}  (mode={mode}, {len(receipts)} receipt{'s' if len(receipts) != 1 else ''})")
    typer.echo()

    # Build a priors map from the trace itself so hash-chain links can resolve.
    actuals = [
        (r["receipt"] if isinstance(r, dict) and "receipt" in r and "version" not in r else r)
        for r in receipts
    ]
    priors = {compute_chain_link(a): a for a in actuals}

    failures = 0
    for idx, actual in enumerate(actuals, start=1):
        ok_flag, stage, detail = _verify_one(actual, mode, priors=priors)
        rid = actual.get("receipt_id", "<no-id>")
        if ok_flag:
            narrate.ok(f"Receipt {idx} [{rid}] → accepted")
        else:
            narrate.fail(f"Receipt {idx} [{rid}] → {stage}: {detail}")
            failures += 1

    typer.echo()
    if failures:
        typer.secho(f"{failures} of {len(receipts)} failed verification.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(f"All {len(receipts)} receipt(s) verified.", fg=typer.colors.GREEN)


# ── inspect ────────────────────────────────────────────────────────


@app.command()
def inspect(
    file: Path = typer.Argument(..., help="Path to a receipt JSON file."),
) -> None:
    """Pretty-print a receipt for human review.

    Shows who/what/when, the principal/issuer/counterparty triangle, the
    populated optional sub-objects (evidence, jurisdiction, accessibility),
    and the action's machine_payload at a glance.
    """
    body = _load(file)
    receipt = body["receipt"] if isinstance(body, dict) and "receipt" in body and "version" not in body else body

    if not isinstance(receipt, dict):
        typer.secho("error: inspect operates on a single receipt, not a trace.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    narrate.section("Receipt")
    narrate.kv("version",    receipt.get("version", "?"))
    narrate.kv("receipt_id", receipt.get("receipt_id", "?"))
    narrate.kv("issued_at",  receipt.get("issued_at", "?"))
    narrate.kv("issuer",     receipt.get("issuer_did", "?"))
    narrate.kv("principal",  receipt.get("principal_did", "?"))

    action = receipt.get("action", {})
    narrate.section("Action")
    narrate.kv("category",   action.get("category", "?"))
    narrate.kv("outcome",    action.get("outcome", "?"))
    narrate.kv("summary",    action.get("human_summary", "?"))
    if "counterparty_label" in action:
        narrate.kv("counterparty", action["counterparty_label"])
    if "counterparty_did" in action:
        narrate.kv("cp_did",   action["counterparty_did"])
    if "amount" in action:
        amt = action["amount"]
        narrate.kv("amount",   f"{amt.get('cents', 0)/100:.2f} {amt.get('currency', '')}")
    if "granted_by_receipt_id" in action:
        narrate.kv("granted_by", action["granted_by_receipt_id"])
    if "reversal_of_receipt_id" in action:
        narrate.kv("reverses",  action["reversal_of_receipt_id"])
    if "machine_payload" in action:
        narrate.kv("payload",   json.dumps(action["machine_payload"], ensure_ascii=False))

    if "authority_chain" in receipt:
        narrate.section("Authority chain (top-level)")
        for entry in receipt["authority_chain"]:
            narrate.kv("•", entry, key_width=1)

    if "previous_receipt_hash" in receipt:
        narrate.section("Hash chain")
        narrate.kv("prev_hash", receipt["previous_receipt_hash"])

    if "jurisdiction" in receipt:
        narrate.section("Jurisdiction")
        for k, v in receipt["jurisdiction"].items():
            narrate.kv(k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)

    if "accessibility" in receipt:
        narrate.section("Accessibility")
        acc = receipt["accessibility"]
        narrate.kv("language",  acc.get("summary_language", "—"))
        if "alt_summaries" in acc:
            narrate.kv("alt_langs", ", ".join(s["lang"] for s in acc["alt_summaries"]))
        if "complexity_level" in acc:
            narrate.kv("complexity", acc["complexity_level"])
        if "requires_review" in acc:
            narrate.kv("review_req", str(acc["requires_review"]))

    if "evidence" in receipt:
        narrate.section("Evidence")
        ev = receipt["evidence"]
        if "external_refs" in ev:
            narrate.kv("refs",      ", ".join(ev["external_refs"]))
        if "prompt_lineage_hash" in ev:
            narrate.kv("prompt_h",  ev["prompt_lineage_hash"])
        if "decision_trace_hash" in ev:
            narrate.kv("decision_h", ev["decision_trace_hash"])
        if "tool_invocations" in ev:
            narrate.kv("tools",     f"{len(ev['tool_invocations'])} invocation(s)")
        if "witness_signatures" in ev:
            narrate.kv("witnesses", f"{len(ev['witness_signatures'])} co-signer(s)")

    typer.echo()


# ── render ─────────────────────────────────────────────────────────


@app.command()
def render(
    file: Path = typer.Argument(..., help="Path to a receipt JSON file (or an array of receipts)."),
    show_crypto: bool = typer.Option(
        False,
        "--show-crypto",
        help="Include DIDs, UUIDs, hashes, and a signature snippet. Drops back into the developer view.",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        help="BCP 47 language tag (e.g. 'de-DE', 'ja-JP', 'es'). If accessibility.alt_summaries has a match, render that instead of the primary summary (spec §9.2).",
    ),
) -> None:
    """Render a receipt or trace as a human-facing diary entry.

    The Agency Log view from spec §10.1 — what the principal sees in their
    diary application. Drops DIDs, UUIDs, hashes, and signatures by default;
    the cryptographic guarantees those provide live BEHIND the rendering,
    not IN it.

    Every receipt is verified before rendering. Forged or malformed receipts
    are rendered with a prominent warning instead of a misleading ✓ — the
    body is still shown for reference but the human is told not to rely on
    it. For arrays of receipts, sorts by issued_at and surfaces both
    authority links and previous_receipt_hash links inline.
    """
    body = _load(file)
    if isinstance(body, list):
        text = _render.render_trace(body, show_crypto=show_crypto, lang=lang)
    else:
        receipt = (
            body["receipt"]
            if isinstance(body, dict) and "receipt" in body and "version" not in body
            else body
        )
        text = _render.render_receipt(receipt, show_crypto=show_crypto, lang=lang)
    typer.echo(text)


# ── walk-authority ─────────────────────────────────────────────────


def _walk_authority_edge(child: dict, parent: dict) -> Optional[str]:
    """Return None if the edge passes spec §4.5 checks 1-5, else an error string."""
    cid = child["receipt_id"]
    pid = parent["receipt_id"]
    if child["action"].get("granted_by_receipt_id") != pid:
        return f"{cid}: granted_by_receipt_id != {pid}"
    if child["principal_did"] != parent["principal_did"]:
        return f"{cid}: principal_did differs from parent grant"
    if parent["action"]["category"] != "authority_granted":
        return f"{cid}: parent {pid} is not authority_granted"
    mp = parent["action"].get("machine_payload", {})
    expires = mp.get("grant_expires_at", "")
    if expires and expires <= child["issued_at"]:
        return f"{cid}: parent grant expired ({expires} <= {child['issued_at']})"
    scope = mp.get("granted_scope", [])
    cat = child["action"]["category"]
    if cat not in scope and "*" not in scope:
        return f"{cid}: action category {cat!r} not in parent's scope {scope}"
    return None


@app.command(name="walk-authority")
def walk_authority(
    file: Path = typer.Argument(..., help="Path to a trace JSON file (array of receipts)."),
    start: Optional[str] = typer.Option(None, "--start", help="Receipt id to start the walk from. Defaults to the last receipt in the file."),
) -> None:
    """Walk action.granted_by_receipt_id back to the root grant.

    For each hop, runs spec §4.5 strict-mode checks: same principal, parent
    is a grant, grant unexpired, child's category in parent's granted_scope.
    """
    body = _load(file)
    if not isinstance(body, list):
        typer.secho("error: walk-authority requires a trace (array of receipts).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    by_id = {r["receipt_id"]: r for r in body}
    current = by_id[start] if start else body[-1]

    narrate.section("Authority chain walk")
    typer.echo()
    chain: list[dict] = [current]
    errors: list[str] = []

    while gid := current["action"].get("granted_by_receipt_id"):
        if gid not in by_id:
            errors.append(f"chain references unknown receipt {gid}")
            break
        parent = by_id[gid]
        err = _walk_authority_edge(current, parent)
        if err:
            errors.append(err)
        chain.append(parent)
        current = parent

    # Render
    for depth, r in enumerate(chain):
        prefix = "  " + ("└─ " if depth > 0 else "   ")
        prefix = prefix if depth == 0 else "  " + ("  " * (depth - 1)) + "└─ "
        category = r["action"]["category"]
        issuer = r["issuer_did"]
        typer.echo(f"{prefix}{r['receipt_id']}")
        typer.secho(
            f"{' ' * (len(prefix))}category: {category}   issuer: {issuer}",
            fg=typer.colors.BRIGHT_BLACK,
        )

    typer.echo()
    if errors:
        for e in errors:
            narrate.fail(e)
        raise typer.Exit(code=1)

    narrate.ok(f"chain length = {len(chain)}; root grant = {chain[-1]['receipt_id']}")
    narrate.note(f"root principal = {chain[-1]['issuer_did']}")


# ── walk-chain ─────────────────────────────────────────────────────


@app.command(name="walk-chain")
def walk_chain(
    file: Path = typer.Argument(..., help="Path to a receipt that declares previous_receipt_hash."),
    back_to: Path = typer.Option(..., "--back-to", help="Path to the prior receipt (we recompute its canonical hash and compare)."),
) -> None:
    """Verify a previous_receipt_hash link between two receipts.

    Loads the prior receipt, JCS-canonicalizes its full body (including
    signature), sha256s the bytes, and compares against the current
    receipt's previous_receipt_hash field.
    """
    cur = _load(file)
    prev = _load(back_to)
    if isinstance(cur, dict) and "receipt" in cur and "version" not in cur:
        cur = cur["receipt"]
    if isinstance(prev, dict) and "receipt" in prev and "version" not in prev:
        prev = prev["receipt"]

    declared = cur.get("previous_receipt_hash")
    if not declared:
        typer.secho("error: current receipt has no previous_receipt_hash.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    recomputed = compute_chain_link(prev)
    narrate.section("Hash chain link")
    narrate.kv("declared",   declared)
    narrate.kv("recomputed", recomputed)

    if declared == recomputed:
        narrate.ok("hash chain link verified")
        return
    narrate.fail("hash chain link MISMATCH — chain broken or wrong prior")
    raise typer.Exit(code=1)


# ── vectors list / vectors run ─────────────────────────────────────


@vectors_app.command("list")
def vectors_list(
    positive: bool = typer.Option(False, "--positive", help="Show only verify_pass vectors."),
    negative: bool = typer.Option(False, "--negative", help="Show only failure vectors."),
) -> None:
    """List the in-repo golden vectors with one-line descriptions."""
    metas = corpus.list_vectors()
    if positive:
        metas = [m for m in metas if m.expected_outcome == "verify_pass"]
    if negative:
        metas = [m for m in metas if m.expected_outcome != "verify_pass"]

    typer.echo()
    for m in metas:
        badge = (
            typer.style("PASS", fg=typer.colors.GREEN)
            if m.expected_outcome == "verify_pass"
            else typer.style(m.expected_outcome.upper(), fg=typer.colors.YELLOW)
        )
        typer.echo(f"  {m.vector_id:<32} {badge:>20}  {m.description}")
    typer.echo()
    typer.secho(f"{len(metas)} vector(s).", fg=typer.colors.BRIGHT_BLACK)


@vectors_app.command("run")
def vectors_run(
    vector_id: str = typer.Argument(..., help="Vector id (e.g. '01-basic-purchase'). See `arp vectors list`."),
) -> None:
    """Load a golden vector, verify it, and explain whether the outcome matches expectations."""
    try:
        meta = corpus.get_vector(vector_id)
    except KeyError as e:
        typer.secho(f"error: {e.args[0]}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    body = meta.load()
    receipt = body["receipt"]
    expected = meta.expected_outcome
    mode = meta.verifier_mode

    narrate.section(f"Vector {meta.vector_id}")
    narrate.kv("description", meta.description)
    narrate.kv("expected",    f"{expected} (mode={mode})")
    narrate.kv("spec_ref",    body.get("spec_ref", "—"))
    typer.echo()

    ok_flag, stage, detail = _verify_one(receipt, mode, priors=corpus.chain_priors())
    if expected == "verify_pass":
        if ok_flag:
            narrate.ok(f"verified — stage={stage}")
        else:
            narrate.fail(f"expected pass but got {stage}: {detail}")
            raise typer.Exit(code=1)
    else:
        # Negative vector — failure at the expected stage is success.
        expected_stage_map = {
            "schema_fail": "schema",
            "signature_fail": "signature",
            "hash_chain_fail": "hash_chain",
        }
        want_stage = expected_stage_map.get(expected, "?")
        if not ok_flag and stage == want_stage:
            narrate.ok(f"correctly rejected at stage={stage}: {detail}")
        else:
            narrate.fail(
                f"expected fail at {want_stage}, got ok={ok_flag} stage={stage} detail={detail!r}"
            )
            raise typer.Exit(code=1)


# ── demo ───────────────────────────────────────────────────────────


def _demo_step(idx: int, total: int, vector_id: str, blurb: str) -> bool:
    """Run one step of the demo; return True if it matched its expected outcome."""
    if vector_id == "nanda_interaction_trace":
        return _demo_step_nanda(idx, total, blurb)

    meta = corpus.get_vector(vector_id)
    body = meta.load()
    receipt = body["receipt"]
    expected = meta.expected_outcome
    mode = meta.verifier_mode

    title = (
        "A single receipt" if vector_id == "01-basic-purchase"
        else "Tampering is detected" if vector_id == "16-invalid-signature"
        else "Tamper-evident hash chain over time" if vector_id == "12-chain-linked"
        else "Regulatory-grade evidence" if vector_id == "04-data-shared-gdpr"
        else "MCP tool integration" if vector_id == "15-with-tool-invocations"
        else "Forward compatibility" if vector_id == "22-unknown-category-tolerant"
        else meta.vector_id
    )
    narrate.step_header(idx, total, title)
    narrate.kv("vector",  meta.vector_id)
    narrate.kv("blurb",   blurb)
    typer.echo()

    ok_flag, stage, detail = _verify_one(receipt, mode, priors=corpus.chain_priors())

    if expected == "verify_pass" and ok_flag:
        narrate.ok(f"verified (schema + Ed25519 signature, mode={mode})")
        _demo_key_facts(receipt)
        return True
    if expected != "verify_pass" and not ok_flag:
        narrate.fail(f"REJECTED at stage={stage} — {detail}")
        narrate.note(f"This is the expected outcome for {meta.vector_id}.")
        return True
    narrate.fail(f"UNEXPECTED: ok={ok_flag} stage={stage} {detail}")
    return False


def _demo_key_facts(receipt: dict) -> None:
    """Print 3-5 lines highlighting the field that makes this vector interesting."""
    action = receipt.get("action", {})
    cat = action.get("category", "?")
    narrate.kv("category", cat)
    narrate.kv("summary",  action.get("human_summary", "?"))

    if "previous_receipt_hash" in receipt:
        narrate.kv("prev_hash", receipt["previous_receipt_hash"])

    if cat == "data_shared" and "jurisdiction" in receipt:
        j = receipt["jurisdiction"]
        narrate.kv("jurisdiction", f"residence={j.get('principal_residence', '?')}, regimes={j.get('applicable_regimes', [])}")
        acc = receipt.get("accessibility", {})
        if "alt_summaries" in acc:
            langs = ", ".join(s["lang"] for s in acc["alt_summaries"])
            narrate.kv("alt_langs", langs)
        if acc.get("requires_review"):
            narrate.kv("flag",     "requires_review=true (sensitive)")

    if "tool_invocations" in receipt.get("evidence", {}):
        ti = receipt["evidence"]["tool_invocations"]
        narrate.kv("tools",     f"{len(ti)} MCP invocation(s) — req+resp hashed")
        narrate.kv("mcp_uri",   ti[0].get("mcp_server_uri", "—"))

    if cat == "other":
        mp = action.get("machine_payload", {})
        narrate.kv("custom_label", mp.get("action_type_label", "—"))


def _demo_step_nanda(idx: int, total: int, blurb: str) -> bool:
    """Run the NANDA causal trace step — walks the authority chain and reports."""
    narrate.step_header(idx, total, "Cross-principal authority graph")
    narrate.kv("trace",  str(corpus.NANDA_TRACE.relative_to(corpus.REPO_ROOT)))
    narrate.kv("blurb",  blurb)
    typer.echo()

    if not corpus.NANDA_TRACE.is_file():
        narrate.fail("nanda_interaction_trace.json missing — run `python nanda/nanda_trace_demo.py` first")
        return False

    trace = json.loads(corpus.NANDA_TRACE.read_text())
    by_id = {r["receipt_id"]: r for r in trace}
    errors: list[str] = []
    for r in trace:
        ok_flag, stage, detail = _verify_one(r, "strict")
        if not ok_flag:
            errors.append(f"{r['receipt_id']}: {stage}: {detail}")

    if errors:
        for e in errors:
            narrate.fail(e)
        return False

    narrate.ok("all 3 receipts verified")

    last = trace[-1]
    chain = [last]
    cur = last
    while gid := cur["action"].get("granted_by_receipt_id"):
        cur = by_id[gid]
        chain.append(cur)

    typer.echo()
    for depth, r in enumerate(chain):
        indent = "  " + ("  " * depth)
        arrow = "└─ granted_by → " if depth > 0 else ""
        typer.echo(f"{indent}{arrow}{r['receipt_id']}  ({r['action']['category']})")

    typer.echo()
    narrate.note(f"root principal: {chain[-1]['issuer_did']}")
    return True


@app.command()
def demo() -> None:
    """The 5-step ARP tour. Reads only — no keys, no network. Idempotent."""
    narrate.banner("ARP v0.1 demo — the format in five steps")
    narrate.note(f"corpus: {corpus.VECTORS_DIR.relative_to(corpus.REPO_ROOT)} ({len(corpus.list_vectors())} vectors)")
    narrate.note(f"trace:  {corpus.NANDA_TRACE.relative_to(corpus.REPO_ROOT)} (if present)")

    total = len(corpus.DEMO_SPINE)
    failures = 0
    for idx, (vid, blurb) in enumerate(corpus.DEMO_SPINE, start=1):
        if not _demo_step(idx, total, vid, blurb):
            failures += 1

    typer.echo()
    if failures:
        narrate.closing(f"{failures} of {total} steps failed — see output above")
        raise typer.Exit(code=1)
    narrate.closing(
        "ARP receipts give humans portable, signed, machine-verifiable proof of"
    )
    typer.secho(
        "  what their agents did — and under what authority.",
        bold=True,
    )
    narrate.divider()


# ── write-side: keygen, issue, grant, revoke ──────────────────────


def _emit_receipt(receipt: dict, out: Optional[Path]) -> None:
    """Write the receipt to --out or stdout, then verify it (paranoia)."""
    text = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if out:
        out.write_text(text)
        typer.secho(f"wrote {out}", fg=typer.colors.GREEN)
    else:
        typer.echo(text, nl=False)

    # Self-check: a receipt we just signed should always verify.
    ok_flag, stage, detail = _verify_one(receipt, mode="strict")
    if not ok_flag:
        typer.secho(
            f"\nWARNING: emitted receipt failed self-verification at {stage}: {detail}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


def _resolve_seed(spec: str) -> bytes:
    """Parse --issuer-key and warn if it's a well-known demo seed."""
    try:
        seed = _issue.parse_seed(spec)
    except ValueError as e:
        typer.secho(f"error: --issuer-key: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if _issue.seed_is_well_known(seed):
        typer.secho(
            "warning: this is a well-known demo seed; do not sign production traffic with it.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    return seed


@app.command()
def keygen(
    seed: Optional[str] = typer.Option(
        None,
        "--seed",
        help="Use a specific 32-byte ASCII seed (demo only). Default: cryptographically random.",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write base64(seed) to this file (mode 0600). If omitted, prints seed to stdout."
    ),
) -> None:
    """Generate an Ed25519 keypair and emit its did:key.

    Without --out, prints both the did:key and the base64-encoded seed
    (the private key) to stdout — save the seed somewhere safe.

    With --out, writes the seed to a file with mode 0600 and prints
    only the did:key to stdout.
    """
    seed_bytes = (
        _issue.parse_seed(seed) if seed else _issue.random_seed()
    )
    did = _issue.did_key_for_seed(seed_bytes)
    seed_b64 = base64.b64encode(seed_bytes).decode("ascii")

    if out:
        out.write_text(seed_b64 + "\n")
        try:
            out.chmod(0o600)
        except OSError:
            pass
        typer.secho(f"wrote seed to {out} (mode 0600)", fg=typer.colors.GREEN)
        typer.echo(f"did: {did}")
    else:
        typer.echo(f"did:  {did}")
        typer.echo(f"seed: base64:{seed_b64}")
        typer.secho(
            "\nSAVE THE SEED. It is the private key. Anyone with it can sign as this DID.",
            fg=typer.colors.YELLOW,
            err=True,
        )


@app.command()
def issue(
    category: str = typer.Argument(..., help="Action category — see `arp vectors list` for valid values."),
    issuer_key: str = typer.Option(..., "--issuer-key", help="Ed25519 seed: 32-byte ASCII, base64:..., or @path/to/file."),
    principal: str = typer.Option(..., "--principal", help="Principal did:key (the human on whose behalf the agent is acting)."),
    summary: str = typer.Option(..., "--summary", "-s", help="One-sentence human_summary (≤ 280 chars)."),
    outcome: str = typer.Option("completed", "--outcome", help="One of: completed, failed, partial, reversed, pending."),
    counterparty: Optional[str] = typer.Option(None, "--counterparty", help="Counterparty did:key."),
    counterparty_label: Optional[str] = typer.Option(None, "--counterparty-label", help="Human-readable counterparty name."),
    amount_cents: Optional[int] = typer.Option(None, "--amount", help="Amount in cents (negative = outgoing)."),
    currency: str = typer.Option("USD", "--currency", help="ISO 4217 currency (used only if --amount given)."),
    granted_by: Optional[str] = typer.Option(None, "--granted-by", help="receipt_id of the authority_granted receipt that authorizes this action."),
    reverses: Optional[str] = typer.Option(None, "--reverses", help="receipt_id of the receipt this one reverses (issuer must match)."),
    payload: Optional[str] = typer.Option(None, "--payload", help="JSON object for action.machine_payload."),
    receipt_id: Optional[str] = typer.Option(None, "--id", help="Override the receipt_id (default: random UUIDv4)."),
    issued_at: Optional[str] = typer.Option(None, "--issued-at", help="Override issued_at (default: now, UTC second precision)."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the receipt to this file (default: stdout)."),
) -> None:
    """Issue a fresh signed ARP receipt.

    For category=authority_granted or authority_revoked, prefer the
    convenience commands `arp grant` and `arp revoke` — they enforce the
    required machine_payload shape automatically.
    """
    seed = _resolve_seed(issuer_key)
    issuer_did = _issue.did_key_for_seed(seed)

    try:
        mp = _issue.parse_payload(payload)
        action = _issue.build_action(
            category=category,
            human_summary=summary,
            outcome=outcome,
            counterparty_did=counterparty,
            counterparty_label=counterparty_label,
            amount_cents=amount_cents,
            currency=currency,
            granted_by_receipt_id=granted_by,
            reversal_of_receipt_id=reverses,
            machine_payload=mp,
        )
        receipt = _issue.build_receipt(
            issuer_did=issuer_did,
            principal_did=principal,
            action=action,
            receipt_id=receipt_id,
            issued_at=issued_at,
        )
    except ValueError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    _issue.sign(seed, receipt)
    _emit_receipt(receipt, out)


@app.command()
def grant(
    issuer_key: str = typer.Option(..., "--issuer-key", help="Ed25519 seed of the issuer (principal or sub-delegating agent)."),
    principal: str = typer.Option(..., "--principal", help="Principal did:key — the human at the root of the chain. Per spec §4.5 step 2, MUST be the same for every grant in a chain."),
    to: str = typer.Option(..., "--to", help="did:key of the agent receiving the authority."),
    scope: str = typer.Option(..., "--scope", help="Comma-separated action categories (or '*' for any). Example: 'data_shared,message_sent'."),
    expires: str = typer.Option(..., "--expires", help="grant_expires_at — RFC 3339 UTC second-precision (e.g. 2026-12-31T23:59:59Z)."),
    summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Override the auto-generated human_summary."),
    granted_by: Optional[str] = typer.Option(None, "--granted-by", help="receipt_id of the parent grant (set for sub-delegation; omit for genesis grants)."),
    receipt_id: Optional[str] = typer.Option(None, "--id", help="Override the receipt_id."),
    issued_at: Optional[str] = typer.Option(None, "--issued-at", help="Override issued_at."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the receipt to this file."),
) -> None:
    """Emit an authority_granted receipt with the required machine_payload shape.

    Convenience wrapper around `arp issue authority_granted` that fills in
    machine_payload.granted_scope/granted_to_did/grant_expires_at.
    """
    seed = _resolve_seed(issuer_key)
    issuer_did = _issue.did_key_for_seed(seed)
    scope_list = [s.strip() for s in scope.split(",") if s.strip()]
    if not scope_list:
        typer.secho("error: --scope must contain at least one category", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    auto_summary = (
        f"Granted {to} authority over {scope} until {expires}."
        if not granted_by
        else f"Sub-delegated authority over {scope} to {to} until {expires}."
    )

    try:
        action = _issue.build_action(
            category="authority_granted",
            human_summary=summary or auto_summary,
            outcome="completed",
            granted_by_receipt_id=granted_by,
            machine_payload={
                "granted_scope": scope_list,
                "granted_to_did": to,
                "grant_expires_at": expires,
            },
        )
        receipt = _issue.build_receipt(
            issuer_did=issuer_did,
            principal_did=principal,
            action=action,
            receipt_id=receipt_id,
            issued_at=issued_at,
        )
    except ValueError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    _issue.sign(seed, receipt)
    _emit_receipt(receipt, out)


@app.command()
def revoke(
    issuer_key: str = typer.Option(..., "--issuer-key", help="Ed25519 seed of the principal who originally issued the grant."),
    principal: str = typer.Option(..., "--principal", help="Principal did:key — must equal the original grant's principal_did."),
    revokes: str = typer.Option(..., "--revokes", help="receipt_id of the authority_granted receipt being revoked."),
    summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Override the auto-generated human_summary."),
    receipt_id: Optional[str] = typer.Option(None, "--id", help="Override the receipt_id."),
    issued_at: Optional[str] = typer.Option(None, "--issued-at", help="Override issued_at."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the receipt to this file."),
) -> None:
    """Emit an authority_revoked receipt that supersedes a prior grant.

    Per spec §4.5 step 6, strict verifiers reject any action receipt
    referencing a grant that has been revoked before the action's issued_at.
    """
    seed = _resolve_seed(issuer_key)
    issuer_did = _issue.did_key_for_seed(seed)

    try:
        action = _issue.build_action(
            category="authority_revoked",
            human_summary=summary or f"Revoked grant {revokes}.",
            outcome="completed",
            machine_payload={"revokes_receipt_id": revokes},
        )
        receipt = _issue.build_receipt(
            issuer_did=issuer_did,
            principal_did=principal,
            action=action,
            receipt_id=receipt_id,
            issued_at=issued_at,
        )
    except ValueError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    _issue.sign(seed, receipt)
    _emit_receipt(receipt, out)


# ── entry point ────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the `arp` script (set in pyproject.toml [project.scripts])."""
    app()


if __name__ == "__main__":
    main()
