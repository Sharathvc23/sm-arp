# ARP — Agency Receipt Protocol, v0.1

**Status:** Working Draft, v0.1, May 2026.
**Authors:** [Stellarminds.ai](https://stellarminds.ai); intended for open standardization.

## What ARP is

ARP defines a **portable, cryptographically signed Receipt** that an AI agent emits when it takes an action on behalf of a human (or organisation). Every receipt is verifiable by anyone who has the issuer's public key, human-readable in one sentence, and links to a chain of evidence that can substantiate the action under audit or dispute.

The protocol is **runtime-agnostic**. An agent built on Claude, OpenAI, LangGraph, CrewAI, or a custom stack can emit ARP receipts. The receipts are interpretable by any client — a portal, a regulator, an insurer, a downstream agent, the human's own diary application.

ARP sits above [Model Context Protocol] (tool integration) and [Agent-to-Agent] (transport). It does not replace either; it is the human-facing accountability layer those protocols deliberately do not address.

## Why ARP exists

When an agent acts on behalf of a human today, the human has no standardized, verifiable, human-readable record of what was done. Conversation transcripts are too low-level. Vendor receipts (Stripe, Uber, Amazon) are scoped to one merchant and tell the human nothing about *why* the agent chose that action. There is no cryptographic link binding an action to the agent that took it or the human it represents, and no way for a third party to audit or dispute the action with evidence.

As agents move from chat-only assistants to systems that purchase, file, decide, transfer, and negotiate on behalf of humans, this gap becomes a public-safety, regulatory, and consumer-trust problem. ARP is the substrate that makes such delegation legible.

## What this directory contains

| Path | Purpose |
|---|---|
| `spec.md` | The full normative specification — RFC-style. **Source of truth.** |
| `conformance.md` | ARP conformance criteria; points at [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) for the signed badge. |
| `dat-companion.md` | One-page sketch of the companion Delegated Authority Token spec referenced by ARP's `authority_chain`. **DRAFT, not normative.** |
| `governance.md` | Stewardship, change process, and the path to public publication. |
| `CHANGELOG.md` | Per-version history. |
| `../../schema/arp/0.1/` | JSON Schemas (Draft 2020-12) for the receipt envelope. |
| `../../vectors/arp/0.1/` | 22 language-agnostic golden receipt vectors. |
| `../../conformance/arp/` | Reference Python conformance harness that executes the vectors. |

## Status of v0.1

- **Spec:** Complete draft. Reviewable.
- **Schemas:** Complete draft.
- **Vectors:** 22 vectors covering core action categories, hash-chain semantics, negative cases, and edge cases.
- **Conformance harness:** `conformance/arp/test_arp_v01.py` — framework-agnostic; any runtime in any language passes the same vectors.

This protocol is **published-spec-first** via [labs.stellarminds.ai/arp](https://labs.stellarminds.ai/arp), not submitted to an external standards body. The signed conformance badge is produced by [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance); see `governance.md` for the path to publication.

## License

MIT — see [LICENSE](../../LICENSE).

---

[Model Context Protocol]: https://modelcontextprotocol.io
[Agent-to-Agent]: https://github.com/a2aproject/A2A
