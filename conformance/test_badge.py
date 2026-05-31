"""Round-trip, tamper, and determinism tests for the conformance badge."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from conformance.badge import (
    VerificationError,
    canonical_json,
    compute_suite_digest,
    derive_did_key,
    load_signing_key,
    parse_did_key,
    sign_envelope,
    verify_envelope,
)
from conformance.verify_badge import main as verify_badge_main


@pytest.fixture
def signing_key() -> bytes:
    return bytes(range(32))


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "runtime": "spec-reference",
        "protocol_versions": ["0.2", "0.3"],
        "suite_digest": "sha256:" + "0" * 64,
        "completed_at": "2026-05-30T12:00:00+00:00",
        "exit_status": 0,
        "passed": 47,
        "failed": 0,
        "skipped": 1,
        "xfailed": 0,
        "xpassed": 0,
    }


def test_canonical_json_sorts_keys(sample_payload: dict[str, Any]) -> None:
    canonical = canonical_json(sample_payload)
    assert canonical.index(b'"completed_at"') < canonical.index(b'"exit_status"')


def test_canonical_json_has_no_whitespace(sample_payload: dict[str, Any]) -> None:
    canonical = canonical_json(sample_payload)
    assert b": " not in canonical
    assert b", " not in canonical
    assert b"\n" not in canonical


def test_canonical_json_is_insertion_order_independent() -> None:
    """Same contents in different insertion order produce identical bytes."""
    a = {"a": 1, "b": 2, "c": 3}
    b = {"c": 3, "b": 2, "a": 1}
    assert canonical_json(a) == canonical_json(b)


def test_did_key_roundtrip() -> None:
    pubkey = bytes(range(32))
    did = derive_did_key(pubkey)
    assert did.startswith("did:key:z")
    assert parse_did_key(did) == pubkey


def test_sign_then_verify_succeeds(sample_payload: dict[str, Any], signing_key: bytes) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    assert verify_envelope(envelope) == sample_payload


def test_verify_rejects_tampered_payload(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    envelope["payload"]["passed"] = 999
    with pytest.raises(VerificationError, match="signature verification failed"):
        verify_envelope(envelope)


def test_verify_rejects_tampered_signature(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    sig = bytearray(base64.b64decode(envelope["signature"]))
    sig[0] ^= 0xFF
    envelope["signature"] = base64.b64encode(bytes(sig)).decode("ascii")
    with pytest.raises(VerificationError, match="signature verification failed"):
        verify_envelope(envelope)


def test_verify_rejects_wrong_signer(sample_payload: dict[str, Any], signing_key: bytes) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    different_pubkey = bytes([255] * 32)
    envelope["signed_by"] = derive_did_key(different_pubkey)
    with pytest.raises(VerificationError, match="signature verification failed"):
        verify_envelope(envelope)


def test_verify_rejects_missing_field(sample_payload: dict[str, Any], signing_key: bytes) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    del envelope["signature"]
    with pytest.raises(VerificationError, match="missing required field: signature"):
        verify_envelope(envelope)


def test_verify_rejects_non_didkey_signer(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    envelope["signed_by"] = "did:web:example.com"
    with pytest.raises(VerificationError, match="invalid signed_by"):
        verify_envelope(envelope)


def test_suite_digest_is_deterministic() -> None:
    first = compute_suite_digest()
    second = compute_suite_digest()
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_suite_digest_changes_when_vector_changes(tmp_path: Path) -> None:
    vec_dir = tmp_path / "vectors"
    vec_dir.mkdir()
    (vec_dir / "a.json").write_text('{"cases": []}')
    first = compute_suite_digest(vec_dir)
    (vec_dir / "a.json").write_text('{"cases": [{"id": 1}]}')
    second = compute_suite_digest(vec_dir)
    assert first != second


# -- load_signing_key: distinguish hex from raw without mangling raw bytes -----


def test_load_signing_key_hex_with_trailing_newline(tmp_path: Path) -> None:
    key = bytes(range(32))
    f = tmp_path / "k.hex"
    f.write_text(key.hex() + "\n")
    assert load_signing_key(f) == key


def test_load_signing_key_raw_exactly_32_bytes(tmp_path: Path) -> None:
    key = bytes(range(32))
    f = tmp_path / "k.bin"
    f.write_bytes(key)
    assert load_signing_key(f) == key


def test_load_signing_key_rejects_33_bytes(tmp_path: Path) -> None:
    """A 32-byte raw key + trailing newline is ambiguous — refuse rather than mangle."""
    f = tmp_path / "k.bad"
    f.write_bytes(bytes(range(32)) + b"\n")
    with pytest.raises(ValueError, match="64 hex characters"):
        load_signing_key(f)


def test_load_signing_key_rejects_wrong_length(tmp_path: Path) -> None:
    f = tmp_path / "k.bad"
    f.write_bytes(b"\x00" * 16)
    with pytest.raises(ValueError, match="64 hex characters"):
        load_signing_key(f)


# -- CLI verifier gates -------------------------------------------------------


def _write_signed_badge(tmp_path: Path, signing_key: bytes, **payload_overrides: Any) -> Path:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "runtime": "spec-reference",
        "protocol_versions": ["0.3"],
        "suite_digest": "sha256:" + "0" * 64,
        "completed_at": "2026-05-30T12:00:00+00:00",
        "exit_status": 0,
        "passed": 46,
        "failed": 0,
        "skipped": 1,
        "xfailed": 0,
        "xpassed": 0,
    }
    payload.update(payload_overrides)
    envelope = sign_envelope(payload, signing_key, "2026-05-30T12:00:00+00:00")
    path = tmp_path / "badge.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


def test_cli_rejects_badge_with_failures(
    tmp_path: Path, signing_key: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_signed_badge(tmp_path, signing_key, failed=1, passed=45)
    assert verify_badge_main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "non-passing run" in err
    assert "failed=1" in err


def test_cli_rejects_badge_with_nonzero_exit_status(
    tmp_path: Path, signing_key: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_signed_badge(tmp_path, signing_key, exit_status=1)
    assert verify_badge_main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "non-passing run" in err
    assert "exit_status=1" in err


def test_cli_allow_failures_bypasses_pass_gate(tmp_path: Path, signing_key: bytes) -> None:
    path = _write_signed_badge(tmp_path, signing_key, failed=3, exit_status=1)
    assert verify_badge_main([str(path), "--allow-failures"]) == 0


def test_cli_accepts_passing_badge(tmp_path: Path, signing_key: bytes) -> None:
    path = _write_signed_badge(tmp_path, signing_key)
    assert verify_badge_main([str(path)]) == 0


# -- JSON Schema conformance: the spec's machine-readable companion ----------


SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema" / "arp" / "0.1"
_ENVELOPE_SCHEMA: dict[str, Any] = json.loads(
    (SCHEMA_DIR / "conformance-envelope.schema.json").read_text()
)
_COMMON_SCHEMA: dict[str, Any] = json.loads((SCHEMA_DIR / "common.schema.json").read_text())

_common_resource = DRAFT202012.create_resource(_COMMON_SCHEMA)
_schema_registry: Registry[Any] = Registry().with_resources(
    [
        ("common.schema.json", _common_resource),
        (_COMMON_SCHEMA["$id"], _common_resource),
    ]
)
_ENVELOPE_VALIDATOR = Draft202012Validator(_ENVELOPE_SCHEMA, registry=_schema_registry)


def test_schema_validates_round_trip_envelope(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    _ENVELOPE_VALIDATOR.validate(envelope)


def test_schema_rejects_missing_required_payload_field(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    del envelope["payload"]["passed"]
    with pytest.raises(ValidationError, match="'passed' is a required property"):
        _ENVELOPE_VALIDATOR.validate(envelope)


def test_schema_rejects_wrong_schema_version(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    sample_payload["schema_version"] = 2
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    with pytest.raises(ValidationError):
        _ENVELOPE_VALIDATOR.validate(envelope)


def test_schema_accepts_failing_run(sample_payload: dict[str, Any], signing_key: bytes) -> None:
    """Schema is structural; pass/fail gating lives in the verifier, not schema."""
    sample_payload["failed"] = 3
    sample_payload["exit_status"] = 1
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    _ENVELOPE_VALIDATOR.validate(envelope)


def test_schema_rejects_unknown_top_level_member(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    envelope["rogue_field"] = "nope"
    with pytest.raises(ValidationError, match="Additional properties"):
        _ENVELOPE_VALIDATOR.validate(envelope)


def test_schema_rejects_unknown_payload_member(
    sample_payload: dict[str, Any], signing_key: bytes
) -> None:
    sample_payload["rogue_payload_field"] = "nope"
    envelope = sign_envelope(sample_payload, signing_key, "2026-05-30T12:00:00+00:00")
    with pytest.raises(ValidationError, match="Additional properties"):
        _ENVELOPE_VALIDATOR.validate(envelope)
