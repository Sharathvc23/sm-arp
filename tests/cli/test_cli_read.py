"""Read-side CLI coverage: verify, inspect, walk-authority, walk-chain,
render, vectors, demo. Every test runs the Typer app in-process via
typer.testing.CliRunner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arp_cli.cli import app
from tests.cli.conftest import strip_ansi


# ── arp verify ─────────────────────────────────────────────────────


def test_verify_passes_on_basic_purchase(runner, vectors_dir):
    result = runner.invoke(app, ["verify", str(vectors_dir / "01-basic-purchase.json")])
    assert result.exit_code == 0
    assert "accepted" in strip_ansi(result.output)


def test_verify_passes_on_full_trace(runner, nanda_trace):
    result = runner.invoke(app, ["verify", str(nanda_trace)])
    assert result.exit_code == 0
    assert "All 3 receipt(s) verified" in strip_ansi(result.output)


def test_verify_rejects_tampered_signature(runner, vectors_dir):
    result = runner.invoke(app, ["verify", str(vectors_dir / "16-invalid-signature.json")])
    assert result.exit_code == 1
    text = strip_ansi(result.output)
    assert "signature" in text
    assert "1 of 1 failed" in text


def test_verify_rejects_wrong_version(runner, vectors_dir):
    result = runner.invoke(app, ["verify", str(vectors_dir / "17-wrong-version.json")])
    assert result.exit_code == 1
    assert "schema" in strip_ansi(result.output)


def test_verify_resolves_hash_chain_in_array(runner, vectors_dir, tmp_path):
    # Build a 2-receipt array (vector 11 genesis + 12 linked) so the chain link resolves.
    import json

    v11 = json.loads((vectors_dir / "11-chain-genesis.json").read_text())["receipt"]
    v12 = json.loads((vectors_dir / "12-chain-linked.json").read_text())["receipt"]
    trace_path = tmp_path / "chain.json"
    trace_path.write_text(json.dumps([v11, v12]))
    result = runner.invoke(app, ["verify", str(trace_path)])
    assert result.exit_code == 0, result.output
    assert "All 2 receipt(s) verified" in strip_ansi(result.output)


def test_verify_missing_file_exits_2(runner, tmp_path):
    result = runner.invoke(app, ["verify", str(tmp_path / "nope.json")])
    assert result.exit_code == 2


def test_verify_tolerant_mode_accepts_negative_strict_case(runner, vectors_dir):
    # 22-unknown-category-tolerant passes both strict and tolerant; tolerant
    # mode should always at least accept it.
    result = runner.invoke(
        app,
        ["verify", str(vectors_dir / "22-unknown-category-tolerant.json"), "--mode", "tolerant"],
    )
    assert result.exit_code == 0


# ── arp inspect ────────────────────────────────────────────────────


def test_inspect_renders_rich_vector(runner, vectors_dir):
    result = runner.invoke(app, ["inspect", str(vectors_dir / "04-data-shared-gdpr.json")])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    # Confirm the key sections show up
    assert "Receipt" in text
    assert "Action" in text
    assert "Jurisdiction" in text
    assert "Accessibility" in text
    assert "data_shared" in text
    assert "DE-BY" in text


# ── arp walk-authority ─────────────────────────────────────────────


def test_walk_authority_traces_to_root(runner, nanda_trace):
    result = runner.invoke(app, ["walk-authority", str(nanda_trace)])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "chain length = 3" in text
    assert "root principal" in text


def test_walk_authority_rejects_non_trace_input(runner, vectors_dir):
    # A single receipt (not an array) should fail with usage-error exit code.
    result = runner.invoke(app, ["walk-authority", str(vectors_dir / "01-basic-purchase.json")])
    assert result.exit_code == 2


# ── arp walk-chain ─────────────────────────────────────────────────


def test_walk_chain_verifies_link(runner, vectors_dir):
    result = runner.invoke(
        app,
        [
            "walk-chain",
            str(vectors_dir / "12-chain-linked.json"),
            "--back-to",
            str(vectors_dir / "11-chain-genesis.json"),
        ],
    )
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "hash chain link verified" in text


def test_walk_chain_detects_mismatch(runner, vectors_dir):
    # vector 19 declares a previous_receipt_hash that doesn't match vector 11
    result = runner.invoke(
        app,
        [
            "walk-chain",
            str(vectors_dir / "19-broken-hash-chain.json"),
            "--back-to",
            str(vectors_dir / "11-chain-genesis.json"),
        ],
    )
    assert result.exit_code == 1
    assert "MISMATCH" in strip_ansi(result.output)


# ── arp render ─────────────────────────────────────────────────────


def test_render_single_receipt_shows_VERIFIED(runner, vectors_dir):
    result = runner.invoke(app, ["render", str(vectors_dir / "01-basic-purchase.json")])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "VERIFIED" in text
    assert "Bought 2 tickets" in text


def test_render_forged_shows_warning(runner, vectors_dir):
    result = runner.invoke(app, ["render", str(vectors_dir / "16-invalid-signature.json")])
    assert result.exit_code == 0  # render returns 0; the warning is the signal
    text = strip_ansi(result.output)
    assert "FORGED" in text
    assert "do not rely on these contents" in text
    # Should NOT show a green checkmark next to the body
    assert "  ✓ Bought a coffee" not in text


def test_render_malformed_shows_warning(runner, vectors_dir):
    result = runner.invoke(app, ["render", str(vectors_dir / "18-oversized-summary.json")])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "MALFORMED" in text


def test_render_trace_surfaces_authority_links(runner, nanda_trace):
    result = runner.invoke(app, ["render", str(nanda_trace)])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "VERIFIED" in text
    # Authority chain prose
    assert "under authority granted at" in text


def test_render_trace_surfaces_hash_chain_links(runner, vectors_dir, tmp_path):
    import json

    v11 = json.loads((vectors_dir / "11-chain-genesis.json").read_text())["receipt"]
    v12 = json.loads((vectors_dir / "12-chain-linked.json").read_text())["receipt"]
    trace_path = tmp_path / "chain.json"
    trace_path.write_text(json.dumps([v11, v12]))
    result = runner.invoke(app, ["render", str(trace_path)])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "follows tamper-chain from earlier receipt" in text


def test_render_lang_picks_alt_summary(runner, vectors_dir):
    result = runner.invoke(
        app,
        ["render", str(vectors_dir / "13-multilang-summary.json"), "--lang", "ja-JP"],
    )
    assert result.exit_code == 0
    # The Japanese summary contains "ロボティクス"
    assert "ロボティクス" in result.output


def test_render_lang_prefix_match(runner, vectors_dir):
    result = runner.invoke(
        app,
        ["render", str(vectors_dir / "13-multilang-summary.json"), "--lang", "es"],
    )
    assert result.exit_code == 0
    # The Spanish summary contains "Respondiste"
    assert "Respondiste" in result.output


def test_render_show_crypto_exposes_dids(runner, nanda_trace, tmp_path):
    import json

    r3 = json.loads(nanda_trace.read_text())[-1]
    p = tmp_path / "r3.json"
    p.write_text(json.dumps(r3))
    result = runner.invoke(app, ["render", str(p), "--show-crypto"])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "did:key:z" in text
    assert "signature:" in text


# ── arp vectors ────────────────────────────────────────────────────


def test_vectors_list_shows_all_22(runner):
    result = runner.invoke(app, ["vectors", "list"])
    assert result.exit_code == 0
    assert "22 vector(s)" in strip_ansi(result.output)


def test_vectors_list_positive_filter(runner):
    result = runner.invoke(app, ["vectors", "list", "--positive"])
    assert result.exit_code == 0
    # 15 of the 22 vectors are verify_pass (01-15 + 21 + 22)
    text = strip_ansi(result.output)
    # Should not contain any of the negative ids
    for negative_id in ("16-invalid-signature", "17-wrong-version", "18-oversized-summary"):
        assert negative_id not in text


def test_vectors_run_positive(runner):
    result = runner.invoke(app, ["vectors", "run", "01-basic-purchase"])
    assert result.exit_code == 0
    assert "verified" in strip_ansi(result.output)


def test_vectors_run_negative_correctly_rejects(runner):
    result = runner.invoke(app, ["vectors", "run", "16-invalid-signature"])
    assert result.exit_code == 0  # the vector failing IS the expected outcome
    assert "correctly rejected" in strip_ansi(result.output)


def test_vectors_run_unknown_id(runner):
    result = runner.invoke(app, ["vectors", "run", "does-not-exist"])
    assert result.exit_code == 2
    assert "unknown vector" in strip_ansi(result.output)


# ── arp demo ───────────────────────────────────────────────────────


def test_demo_exits_zero_and_walks_seven_steps(runner):
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    text = strip_ansi(result.output)
    # All 7 spine steps should appear
    assert "Step 1/7" in text
    assert "Step 7/7" in text
    # And the closing banner
    assert "ARP receipts give humans portable" in text


def test_demo_includes_authority_chain_walk(runner):
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "Cross-principal authority graph" in text
    assert "granted_by" in text
