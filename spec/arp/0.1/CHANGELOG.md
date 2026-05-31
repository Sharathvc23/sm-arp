# ARP Changelog

## v0.1 — 2026-05-21 — Initial Working Draft

First public draft. Incubated in `spec/arp/0.1/` inside the NANDA Chapter Protocol umbrella repository alongside the reference implementation.

### Spec highlights

- Receipt envelope shape with required and optional members.
- Action object with 18 normative categories plus `other`.
- Evidence object: screenshots, external refs, prompt and decision lineage hashes, MCP tool invocations, witness signatures.
- Canonical signing via RFC 8785 JCS + Ed25519.
- Optional per-issuer hash chain via `previous_receipt_hash`.
- Jurisdiction block — residence, action locus, data residency, applicable regimes, consent evidence.
- Accessibility block — language tagging, alt summaries, screen-reader hints, complexity level, review-requested flag.
- Three visibility tiers (principal / counterparty / public) with deterministic redaction.
- Security considerations covering forgery, replay, hash-chain tamper, repudiation, privacy.
- Forward-compatibility via namespace-prefixed `extensions` and unknown-category tolerant mode.

### Reference implementation

- `chapter/arp.py` — verification, storage, hash chain.
- `member-sdk/community_member/arp.py` — emit, sign, push, agency-log persistence.
- `conformance/arp/test_arp_v01.py` — 20+ vector suite.

### Companion drafts

- `dat-companion.md` — Delegated Authority Token sketch (NOT normative in v0.1).

### What's deferred to v0.2

- Normative DAT.
- Commitment / WorkProduct sub-objects (currently `commitment_*` categories are placeholders).
- Per-category `machine_payload` schemas.
- Receipt revocation envelope (today done implicitly via `outcome=reversed`).
- Multi-principal actions.
- EU AI Act Article 13 mapping appendix.

## v0.1.1 — 2026-05-30 — Conformance Badge

- Added `conformance.md` — normative spec for the ARP Conformance Badge envelope, the signed self-attestation a runtime ships at `.nanda/conformance.json`.
- Added `schema/arp/0.1/conformance-envelope.schema.json` — JSON Schema bound to the spec.
- Reference implementation: `conformance/badge.py`, `conformance/verify_badge.py`, `conformance/conftest.py` `--sign-with` and `--runtime-name` flags. 26-test round-trip + tamper + schema + pass-gate suite in `conformance/test_badge.py`.
- Side-effect fix: `conformance/server/conftest.py` `pytest_collection_modifyitems` scope was too broad and was suppressing 225 non-server tests — narrowed to items rooted at `conformance/server/`.

### What conformance.md establishes

- A signed badge proves authorship and a claim, **not** verified conformance. Registry admission requires lab re-run, counter-signature, or attested CI.
- Default verifier behavior enforces both signature verification (§9.1–§9.5) and a pass-gate (§9.7: `failed == 0` and `exit_status == 0`). The pass-gate is configurable off via `--allow-failures`.
- `suite_digest` pins the **vector corpus present at run time**, not "what passed" — an adapter-scoped run does not exercise every vector.

### What's deferred

- Badge vector files under `vectors/arp/0.1/conformance/` (7 vectors listed in conformance.md §12) — to be produced as a follow-on, deterministic and byte-stable, to support cross-language verifiers.

## v0.1.3 — 2026-05-31 — Governance pivot to published-spec-first

Per the standards-path decision recorded in the project's memory, ARP is **published-spec-first** via `labs.stellarminds.ai/arp`, not submitted to any external standards body for v0.1. This entry records the cleanup pass:

- `spec/arp/0.1/governance.md` §3 rewritten — three-stage path (Incubation → Standalone repo → Public publication) replaces the prior Linux Foundation Agentic AI Foundation submission story.
- `spec/arp/0.1/governance.md` §4 rewritten — "ARP" and the conformance Mark are Stellarminds-controlled, with mark policy at `labs.stellarminds.ai/conformance/mark-policy` (forthcoming).
- `spec/arp/0.1/lf-submission-draft.md` deleted — no longer applicable.
- `spec/arp/0.1/README.md`, `spec/arp/0.1/spec.md` §16, `spec/arp/0.1/dat-companion.md`: LF references replaced with the labs.stellarminds.ai/arp framing.
- Root README.md updated to match.
- `spec/arp/EXTRACTION.md` rewritten to target `Sharathvc23/arp-spec` directly and to include the v0.1 badge program artifacts (badge.py + verify_badge.py + envelope schema + 7 badge vectors) in the extraction set.
- New `scripts/extract-arp-spec.sh` carries out the file moves and writes a fresh standalone README, pyproject, and CI workflow. Tested: the extracted repo's `pytest conformance/` reports 63 passed in isolation.

No wire-protocol or semantic change. Receipt envelope, badge envelope, schemas, and vectors are unchanged.

## v0.1.2 — 2026-05-30 — Badge vectors land

- Produced the 7 badge vectors promised in `conformance.md` §12 — `valid-signed-badge`, `tampered-payload`, `tampered-signature`, `wrong-signer`, `non-didkey-signer`, `missing-signature`, `failing-run`. They live at `vectors/arp/0.1/conformance/*.json`.
- Added `conformance/_badge_vector_gen.py` — deterministic regenerator. Fixed seed key + fixed RFC 3339 timestamps + fixed payload contents → byte-identical files on re-run. Cross-language verifiers can compare against the same JSON files.
- Added `conformance/test_badge_vectors.py` — 12 tests verifying that each vector's `expected_outcome` matches what `verify_envelope` (and the CLI's pass-gate) actually produces, plus a byte-stability test that re-signs in-memory and asserts equality with the on-disk envelope.
- Re-signed all three runtime badges (`member-sdk`, `chapter`, `openclaw-skill`) — adding new files under `vectors/` shifts `suite_digest`, which (by design) invalidates every prior badge until regenerated. That's the drift-detection contract working as documented.
