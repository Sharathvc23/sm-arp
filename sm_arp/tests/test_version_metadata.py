"""``__version__`` must equal the installed distribution version.

sm-arp previously exported **no** ``__version__`` at all. That is worse than a
wrong one: ``getattr(sm_arp, "__version__", default)`` silently returns the
*caller's* fallback, so a consumer's defensive version check reports whatever
it guessed and looks like it succeeded. sm-arp is the most depended-on package
in the org, so that silence propagated furthest.

A literal would be no better — it is a second copy of pyproject's ``version``
with nothing comparing them, which is exactly how sm-provision 0.1.0 shipped as
"0.0.1" and sm-authority 0.1.0 shipped the same wrong value from the same
template.

These tests fail on that *shape* rather than on a specific wrong number.
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import version as dist_version
from pathlib import Path

import pytest

import sm_arp


def test_dunder_version_equals_installed_distribution_version() -> None:
    assert sm_arp.__version__ == dist_version("sm-arp")


def test_dunder_version_is_not_the_uninstalled_sentinel() -> None:
    # The source-tree fallback must never reach an installed environment; if it
    # does, every consumer's version check silently reads a placeholder.
    assert sm_arp.__version__ != "0.0.0.dev0"


def test_module_source_declares_no_version_literal() -> None:
    """The regression guard proper.

    Equality above passes the moment someone re-adds a literal that happens to
    match today. This fails on the *duplication* — the thing that drifts — so a
    future hand-maintained copy is rejected even while it is still correct.
    """
    src = Path(sm_arp.__file__).read_text(encoding="utf-8")
    literals = re.findall(r'^__version__\s*=\s*["\']', src, flags=re.MULTILINE)
    assert not literals, (
        "__version__ must be derived from distribution metadata, not assigned a "
        "literal — a literal is a second copy of pyproject's version and drifts."
    )


def test_pyproject_remains_the_single_declared_source() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():  # installed-only test run
        pytest.skip("source checkout not present")
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert declared == dist_version("sm-arp"), (
        "pyproject declares the version; a mismatch here means the installed "
        "wheel was built from a different tree than this checkout."
    )
