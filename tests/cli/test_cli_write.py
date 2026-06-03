"""Write-side CLI coverage: keygen, issue, grant, revoke.

Asserts that every issued receipt round-trips through `arp verify` cleanly —
the strongest guarantee that the write-side hasn't gone subtly wrong.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from arp_cli.cli import app
from tests.cli.conftest import did_for_seed, strip_ansi


# Seeds chosen to NOT collide with the well-known demo seeds, so tests
# don't trip the "well-known seed" warning.
TEST_HUMAN_SEED   = "tests-cli-write-human-32bytes!!!"
TEST_AGENT_SEED   = "tests-cli-write-agent-32-bytes!!"


# ── arp keygen ─────────────────────────────────────────────────────


def test_keygen_with_seed_is_deterministic(runner):
    a = runner.invoke(app, ["keygen", "--seed", TEST_HUMAN_SEED])
    b = runner.invoke(app, ["keygen", "--seed", TEST_HUMAN_SEED])
    assert a.exit_code == 0 and b.exit_code == 0
    # Same seed → same DID
    did_a = next(line.split()[1] for line in strip_ansi(a.output).splitlines() if line.startswith("did:"))
    did_b = next(line.split()[1] for line in strip_ansi(b.output).splitlines() if line.startswith("did:"))
    assert did_a == did_b
    assert did_a.startswith("did:key:z")


def test_keygen_without_seed_is_random(runner):
    a = runner.invoke(app, ["keygen"])
    b = runner.invoke(app, ["keygen"])
    assert a.exit_code == 0 and b.exit_code == 0
    did_a = next(line.split()[1] for line in strip_ansi(a.output).splitlines() if line.startswith("did:"))
    did_b = next(line.split()[1] for line in strip_ansi(b.output).splitlines() if line.startswith("did:"))
    assert did_a != did_b


def test_keygen_out_writes_seed_at_mode_0600(runner, tmp_path):
    seed_file = tmp_path / "seed.key"
    result = runner.invoke(app, ["keygen", "--out", str(seed_file)])
    assert result.exit_code == 0
    assert seed_file.is_file()
    # POSIX permission bits
    assert (seed_file.stat().st_mode & 0o777) == 0o600
    # Contents should be 32-byte base64-encoded seed
    content = seed_file.read_text().strip()
    decoded = base64.b64decode(content, validate=True)
    assert len(decoded) == 32


def test_keygen_short_seed_errors(runner):
    result = runner.invoke(app, ["keygen", "--seed", "too-short"])
    assert result.exit_code != 0


# ── arp issue ──────────────────────────────────────────────────────


def test_issue_message_sent_roundtrips(runner, tmp_path):
    did = did_for_seed(runner, TEST_AGENT_SEED)
    out = tmp_path / "r.json"
    result = runner.invoke(
        app,
        [
            "issue", "message_sent",
            "--issuer-key", TEST_AGENT_SEED,
            "--principal", did,
            "--summary", "Test message from the write-side test suite.",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(out.read_text())
    assert body["version"] == "arp/0.1"
    assert body["issuer_did"] == did
    assert body["action"]["category"] == "message_sent"

    # Round-trip: a freshly issued receipt MUST verify.
    verify_result = runner.invoke(app, ["verify", str(out)])
    assert verify_result.exit_code == 0


def test_issue_with_payload_and_amount(runner, tmp_path):
    did = did_for_seed(runner, TEST_AGENT_SEED)
    out = tmp_path / "r.json"
    result = runner.invoke(
        app,
        [
            "issue", "purchase",
            "--issuer-key", TEST_AGENT_SEED,
            "--principal", did,
            "--summary", "Bought test widget for $9.99.",
            "--amount", "-999",
            "--currency", "USD",
            "--counterparty-label", "Test Counterparty",
            "--payload", '{"sku":"WIDGET-001","qty":1}',
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(out.read_text())
    assert body["action"]["amount"] == {"currency": "USD", "cents": -999}
    assert body["action"]["machine_payload"]["sku"] == "WIDGET-001"


def test_issue_short_seed_errors(runner):
    result = runner.invoke(
        app,
        [
            "issue", "message_sent",
            "--issuer-key", "short",
            "--principal", "did:key:z6MkABCDEFGHIJKLMNOPQRSTUVWXYZ12345",
            "--summary", "x",
        ],
    )
    assert result.exit_code == 2
    assert "seed must be exactly 32 bytes" in result.output


def test_issue_invalid_payload_errors(runner):
    did = did_for_seed(runner, TEST_AGENT_SEED)
    result = runner.invoke(
        app,
        [
            "issue", "purchase",
            "--issuer-key", TEST_AGENT_SEED,
            "--principal", did,
            "--summary", "x",
            "--payload", "not-json",
        ],
    )
    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_issue_malformed_principal_warns_and_exits_nonzero(runner):
    did = did_for_seed(runner, TEST_AGENT_SEED)
    result = runner.invoke(
        app,
        [
            "issue", "message_sent",
            "--issuer-key", TEST_AGENT_SEED,
            "--principal", "not-a-did",
            "--summary", "x",
        ],
    )
    # Schema validation catches it in the self-check after signing.
    assert result.exit_code == 1
    assert "WARNING" in result.output


# ── arp grant ──────────────────────────────────────────────────────


def test_grant_emits_authority_granted_with_required_machine_payload(runner, tmp_path):
    h = did_for_seed(runner, TEST_HUMAN_SEED)
    a = did_for_seed(runner, TEST_AGENT_SEED)
    out = tmp_path / "grant.json"
    result = runner.invoke(
        app,
        [
            "grant",
            "--issuer-key", TEST_HUMAN_SEED,
            "--principal", h,
            "--to", a,
            "--scope", "data_shared,message_sent",
            "--expires", "2026-12-31T23:59:59Z",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    body = json.loads(out.read_text())
    assert body["action"]["category"] == "authority_granted"
    mp = body["action"]["machine_payload"]
    assert mp["granted_scope"] == ["data_shared", "message_sent"]
    assert mp["granted_to_did"] == a
    assert mp["grant_expires_at"] == "2026-12-31T23:59:59Z"

    # The grant itself should verify.
    verify_result = runner.invoke(app, ["verify", str(out)])
    assert verify_result.exit_code == 0


def test_grant_subdelegation_with_granted_by(runner, tmp_path):
    h = did_for_seed(runner, TEST_HUMAN_SEED)
    a = did_for_seed(runner, TEST_AGENT_SEED)
    b = did_for_seed(runner, "tests-cli-write-agent-b-32bytes!")

    # Genesis grant (so we have a real receipt_id to reference)
    g1 = tmp_path / "g1.json"
    runner.invoke(app, [
        "grant", "--issuer-key", TEST_HUMAN_SEED, "--principal", h, "--to", a,
        "--scope", "data_shared,authority_granted", "--expires", "2026-12-31T23:59:59Z",
        "--out", str(g1),
    ])
    g1_id = json.loads(g1.read_text())["receipt_id"]

    # Sub-grant pointing at g1
    g2 = tmp_path / "g2.json"
    result = runner.invoke(app, [
        "grant", "--issuer-key", TEST_AGENT_SEED, "--principal", h, "--to", b,
        "--scope", "data_shared", "--expires", "2026-12-31T23:59:59Z",
        "--granted-by", g1_id,
        "--out", str(g2),
    ])
    assert result.exit_code == 0
    assert json.loads(g2.read_text())["action"]["granted_by_receipt_id"] == g1_id


def test_grant_empty_scope_errors(runner):
    h = did_for_seed(runner, TEST_HUMAN_SEED)
    a = did_for_seed(runner, TEST_AGENT_SEED)
    result = runner.invoke(app, [
        "grant", "--issuer-key", TEST_HUMAN_SEED, "--principal", h, "--to", a,
        "--scope", ",,,", "--expires", "2026-12-31T23:59:59Z",
    ])
    assert result.exit_code == 2


# ── arp revoke ─────────────────────────────────────────────────────


def test_revoke_emits_authority_revoked(runner, tmp_path):
    h = did_for_seed(runner, TEST_HUMAN_SEED)
    target = "10000001-0001-4001-8001-100000000001"  # arbitrary valid UUIDv4 from nanda trace
    out = tmp_path / "revoke.json"
    result = runner.invoke(app, [
        "revoke", "--issuer-key", TEST_HUMAN_SEED, "--principal", h,
        "--revokes", target, "--out", str(out),
    ])
    assert result.exit_code == 0, result.output

    body = json.loads(out.read_text())
    assert body["action"]["category"] == "authority_revoked"
    assert body["action"]["machine_payload"]["revokes_receipt_id"] == target

    # Revocation should verify.
    verify_result = runner.invoke(app, ["verify", str(out)])
    assert verify_result.exit_code == 0
