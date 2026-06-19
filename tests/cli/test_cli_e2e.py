"""End-to-end CLI scenario: build a NANDA-style 3-receipt delegation chain
from scratch using only `arp keygen` / `arp grant` / `arp issue`, then verify
and walk it. This is the same shell story in README_NANDA.md, captured as
a regression net.
"""

from __future__ import annotations

import json

from arp_cli.cli import app
from tests.cli.conftest import did_for_seed, parse_receipt_id, strip_ansi

E2E_HUMAN = "tests-cli-e2e-human-seed-32-bts!"
E2E_AGENT_A = "tests-cli-e2e-agent-a-seed-32bt!"
E2E_AGENT_B = "tests-cli-e2e-agent-b-seed-32bt!"


def test_full_delegation_chain_builds_verifies_and_walks(runner, tmp_path):
    h = did_for_seed(runner, E2E_HUMAN)
    a = did_for_seed(runner, E2E_AGENT_A)
    b = did_for_seed(runner, E2E_AGENT_B)
    assert h != a != b

    # Receipt 1 — Human grants Agent A. scope includes authority_granted so A
    # is permitted to sub-delegate.
    r1 = tmp_path / "r1.json"
    grant1 = runner.invoke(
        app,
        [
            "grant",
            "--issuer-key",
            E2E_HUMAN,
            "--principal",
            h,
            "--to",
            a,
            "--scope",
            "data_shared,message_sent,authority_granted",
            "--expires",
            "2026-12-31T23:59:59Z",
            "--out",
            str(r1),
        ],
    )
    assert grant1.exit_code == 0, grant1.output
    r1_id = parse_receipt_id(r1)

    # Receipt 2 — Agent A sub-delegates to Agent B; principal stays the human.
    r2 = tmp_path / "r2.json"
    grant2 = runner.invoke(
        app,
        [
            "grant",
            "--issuer-key",
            E2E_AGENT_A,
            "--principal",
            h,
            "--to",
            b,
            "--scope",
            "data_shared",
            "--expires",
            "2026-12-31T23:59:59Z",
            "--granted-by",
            r1_id,
            "--out",
            str(r2),
        ],
    )
    assert grant2.exit_code == 0, grant2.output
    r2_id = parse_receipt_id(r2)

    # Receipt 3 — Agent B does the data_shared action under the sub-delegation.
    r3 = tmp_path / "r3.json"
    action = runner.invoke(
        app,
        [
            "issue",
            "data_shared",
            "--issuer-key",
            E2E_AGENT_B,
            "--principal",
            h,
            "--summary",
            "E2E test: shared compliance summary with the NANDA Registry.",
            "--counterparty-label",
            "NANDA Registry",
            "--granted-by",
            r2_id,
            "--payload",
            '{"fields_shared":["compliance_summary"]}',
            "--out",
            str(r3),
        ],
    )
    assert action.exit_code == 0, action.output

    # Bundle into a trace
    trace_path = tmp_path / "trace.json"
    trace = [json.loads(r1.read_text()), json.loads(r2.read_text()), json.loads(r3.read_text())]
    trace_path.write_text(json.dumps(trace, indent=2))

    # Verify the whole trace
    verify_result = runner.invoke(app, ["verify", str(trace_path)])
    assert verify_result.exit_code == 0, verify_result.output
    assert "All 3 receipt(s) verified" in strip_ansi(verify_result.output)

    # Walk the authority chain
    walk_result = runner.invoke(app, ["walk-authority", str(trace_path)])
    assert walk_result.exit_code == 0, walk_result.output
    walk_text = strip_ansi(walk_result.output)
    assert "chain length = 3" in walk_text
    # Root principal is the human
    assert h in walk_text

    # Render produces a clean diary view with VERIFIED pills
    render_result = runner.invoke(app, ["render", str(trace_path)])
    assert render_result.exit_code == 0
    render_text = strip_ansi(render_result.output)
    assert render_text.count("VERIFIED") == 3
    assert "under authority granted at" in render_text


def test_chain_with_tampered_middle_receipt_renders_as_forged(runner, tmp_path):
    """Tamper with Receipt 2 after the chain is built — render must flag it as FORGED."""
    h = did_for_seed(runner, E2E_HUMAN)
    a = did_for_seed(runner, E2E_AGENT_A)
    b = did_for_seed(runner, E2E_AGENT_B)

    r1 = tmp_path / "r1.json"
    runner.invoke(
        app,
        [
            "grant",
            "--issuer-key",
            E2E_HUMAN,
            "--principal",
            h,
            "--to",
            a,
            "--scope",
            "data_shared,authority_granted",
            "--expires",
            "2026-12-31T23:59:59Z",
            "--out",
            str(r1),
        ],
    )
    r1_id = parse_receipt_id(r1)

    r2 = tmp_path / "r2.json"
    runner.invoke(
        app,
        [
            "grant",
            "--issuer-key",
            E2E_AGENT_A,
            "--principal",
            h,
            "--to",
            b,
            "--scope",
            "data_shared",
            "--expires",
            "2026-12-31T23:59:59Z",
            "--granted-by",
            r1_id,
            "--out",
            str(r2),
        ],
    )

    # Tamper: rewrite the human_summary AFTER signing
    r2_body = json.loads(r2.read_text())
    r2_body["action"]["human_summary"] = "TAMPERED — sub-delegation never happened."
    r2.write_text(json.dumps(r2_body))

    # Render must call it out
    render_result = runner.invoke(app, ["render", str(r2)])
    assert render_result.exit_code == 0
    render_text = strip_ansi(render_result.output)
    assert "FORGED" in render_text
    assert "do not rely on these contents" in render_text

    # Verify must reject
    verify_result = runner.invoke(app, ["verify", str(r2)])
    assert verify_result.exit_code == 1
