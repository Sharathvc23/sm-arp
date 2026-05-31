# ARP — Agency Receipt Protocol

**Status:** Working Draft, v0.1, May 2026.
**Authors:** Stewardship by the NANDA Chapter Protocol contributors; intended for open standardization.
**Discussion home:** This directory until the spec is split out to a standalone repository at first publication.

## What ARP is

ARP defines a **portable, cryptographically signed Receipt** that an AI agent emits when it takes an action on behalf of a human (or organisation). Every receipt is verifiable by anyone who has the issuer's public key, human-readable in one sentence, and links to a chain of evidence that can substantiate the action under audit or dispute.

The protocol is **runtime-agnostic**. An agent built on Claude, OpenAI, an OpenClaw skill, LangGraph, CrewAI, or a custom stack can emit ARP receipts. The receipts are interpretable by any client — a portal, a regulator, an insurer, a downstream agent, the human's own diary application.

ARP sits above [Model Context Protocol] (tool integration) and [Agent-to-Agent] (transport). It does not replace either; it is the human-facing accountability layer those protocols deliberately do not address.

## Why ARP exists

When an agent acts on behalf of a human today, the human has no standardized, verifiable, human-readable record of what was done. Conversation transcripts are too low-level. Vendor receipts (Stripe, Uber, Amazon) are scoped to one merchant and tell the human nothing about *why* the agent chose that action. There is no cryptographic link binding an action to the agent that took it or the human it represents, and no way for a third party to audit or dispute the action with evidence.

As agents move from chat-only assistants to systems that purchase, file, decide, transfer, and negotiate on behalf of humans, this gap becomes a public-safety, regulatory, and consumer-trust problem. ARP is the substrate that makes such delegation legible.

## What this directory contains

| Path | Purpose |
|---|---|
| `spec.md` | The full normative specification — RFC-style. **Source of truth.** |
| `conformance.md` | Normative spec for the Conformance Badge — the signed self-attestation a runtime ships at `.nanda/conformance.json`. |
| `dat-companion.md` | One-page sketch of the companion Delegated Authority Token spec referenced by ARP's `authority_chain`. **DRAFT, not normative.** |
| `governance.md` | Stewardship, change process, and the path to public publication via labs.stellarminds.ai/arp. |
| `CHANGELOG.md` | Per-version history once releases are cut. |
| `../../schema/arp/0.1/` | JSON Schemas (Draft 2020-12) for every envelope object — Receipt + Conformance Badge. |
| `../../vectors/arp/0.1/` | Language-agnostic golden test vectors (20+). |
| `../../conformance/arp/` | Reference Python conformance harness that executes the vectors. |
| `../../conformance/badge.py` `+ verify_badge.py` | Reference implementation of the Conformance Badge envelope per `conformance.md`. |

## Status of v0.1

- **Spec:** Complete draft. Reviewable.
- **Schemas:** Complete draft.
- **Vectors:** 20 vectors covering core action categories, hash-chain semantics, negative cases, and edge cases.
- **Reference implementation:**
  - Chapter side — see `chapter/arp.py` and `chapter/chapter_agent.py` `/api/receipts` endpoints.
  - Member SDK side — see `member-sdk/community_member/arp.py`.
  - Conformance harness — see `conformance/arp/test_arp_v01.py`.

This protocol is **published-spec-first** via [labs.stellarminds.ai/arp](https://labs.stellarminds.ai/arp), not submitted to an external standards body. Adoption credibility comes from real production use plus a conformance program operated at `labs.stellarminds.ai/conformance` — see `governance.md` §3 for the path.

## Repo-independence note

ARP is designed to live in its own repository under a permissive license, so any agent runtime can implement it without depending on the NANDA Chapter Protocol. The spec is incubated here because the reference implementation depends on NANDA's existing identity, signing, and ledger primitives. The intended cut-over to a standalone `arp-spec` repository happens at the first public publication of v0.1 RC, at which point this directory will continue to ship the reference implementation but the canonical spec will live in the standalone repo.

## License

The spec and schemas in this directory are released under the MIT License. The reference implementation under `chapter/`, `member-sdk/`, etc. inherits the parent repository's license.

---

[Model Context Protocol]: https://modelcontextprotocol.io
[Agent-to-Agent]: https://github.com/a2aproject/A2A
