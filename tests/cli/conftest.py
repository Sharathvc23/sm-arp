"""Shared fixtures + helpers for arp_cli pytest suites."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arp_cli.cli import app


REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "vectors" / "arp" / "0.1"
NANDA_TRACE = REPO_ROOT / "nanda" / "nanda_interaction_trace.json"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def runner() -> CliRunner:
    """Typer/Click runner that captures stdout, stderr, and exit code in-process."""
    return CliRunner()


@pytest.fixture
def vectors_dir() -> Path:
    return VECTORS_DIR


@pytest.fixture
def nanda_trace() -> Path:
    return NANDA_TRACE


def strip_ansi(text: str) -> str:
    """Strip ANSI styling so tests can assert against the underlying text."""
    return _ANSI_RE.sub("", text)


def did_for_seed(runner: CliRunner, seed: str) -> str:
    """Derive a did:key for a given seed by calling `arp keygen`."""
    result = runner.invoke(app, ["keygen", "--seed", seed])
    assert result.exit_code == 0, result.output
    for line in strip_ansi(result.output).splitlines():
        if line.startswith("did:"):
            return line.split()[1]
    raise AssertionError(f"could not find did: line in keygen output: {result.output!r}")


def parse_receipt_id(path: Path) -> str:
    """Read a receipt JSON file and return its receipt_id."""
    return json.loads(path.read_text())["receipt_id"]
