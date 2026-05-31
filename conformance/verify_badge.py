"""CLI verifier for signed conformance badges.

Usage::

    python -m conformance.verify_badge <path-to-badge.json>
    python -m conformance.verify_badge <path> --expected-suite-digest sha256:<hex>

Exit status:
    0 — badge verifies, and (if asserted) suite_digest matches
    1 — verification failed
    2 — file not found / not JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from conformance.badge import VerificationError, verify_envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a signed NANDA conformance badge",
    )
    parser.add_argument("path", help="Path to .nanda/conformance.json")
    parser.add_argument(
        "--expected-suite-digest",
        default=None,
        help="Optional: assert the badge pins to this suite_digest (format: sha256:<hex>).",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        default=False,
        help=(
            "By default the verifier fails if the badge records failures or "
            "non-zero exit_status. Pass --allow-failures to verify signature only."
        ),
    )
    args = parser.parse_args(argv)

    try:
        envelope = json.loads(Path(args.path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"FAIL: file not found: {args.path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON: {exc}", file=sys.stderr)
        return 2

    try:
        payload = verify_envelope(envelope)
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.expected_suite_digest:
        actual = payload.get("suite_digest")
        if actual != args.expected_suite_digest:
            print(
                f"FAIL: suite_digest mismatch — "
                f"expected {args.expected_suite_digest}, got {actual}",
                file=sys.stderr,
            )
            return 1

    if not args.allow_failures:
        failed = payload.get("failed")
        exit_status = payload.get("exit_status")
        if failed is None or failed != 0 or exit_status != 0:
            print(
                f"FAIL: badge records a non-passing run "
                f"(failed={failed}, exit_status={exit_status}). "
                f"Use --allow-failures to verify signature only.",
                file=sys.stderr,
            )
            return 1

    print(f"OK: signed by {envelope['signed_by']}")
    print(
        f"    runtime={payload.get('runtime')} "
        f"versions={payload.get('protocol_versions')} "
        f"passed={payload.get('passed')} failed={payload.get('failed')}"
    )
    print(f"    suite_digest={payload.get('suite_digest')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
