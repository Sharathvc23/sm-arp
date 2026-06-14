# sm-arp: The Agency Receipt Protocol

*Personal research contribution by [Stellarminds.ai](https://stellarminds.ai), aligned with [Project NANDA](https://projectnanda.org) standards.*

---

## Abstract

The Agency Receipt Protocol (ARP) is a per-action accountability primitive for autonomous AI agents acting on behalf of humans: a signed, human-readable record that an agent took a specific action, for a specific principal, under a specific authority, with a chain of evidence behind it. Each receipt is verifiable by anyone holding the issuing agent's public key, readable in a single sentence by the human it represents, and linkable to the grant of authority the action was taken under. ARP is runtime-agnostic — an agent built on Claude, OpenAI, LangGraph, or a custom stack emits the same receipt — and sits *above* the tool-integration and transport protocols (MCP, A2A) as the human-facing layer those deliberately do not provide.

This whitepaper makes the case that the *receipt* — the portable, human-facing record of an agent's action — is a primitive in its own right, separable from the runtimes that produce it and from the substrate evidence that engines emit. A single receipt proves one action; the *aggregate* of an agent's receipts is the substrate for portable, counterparty-corroborated **reputation** (§8) — a standing any party recomputes and verifies offline. The receipt envelope, signing, evidence model, and authority chain are documented in [`SPEC.md`](spec/arp/0.1/spec.md) as a working draft. This document covers motivation, design choices, composition, and the reputation profile built on the receipt.

---

## 1. Problem

Agents are moving from chat assistants to systems that *act*: they purchase services, file records, agree to terms, transfer funds, book appointments, and dispatch messages on a person's behalf. The human they represent is, increasingly, not in the loop for each action — and has no standardized, verifiable, human-readable record of what was done in their name.

The records that exist today fail the human on every axis:

- **Conversation logs are too low-level.** Thousands of tokens of model trace are not a record a person, a regulator, or an insurer can read or act on. They are not signed, and they do not say *which* of a person's agents took an action or *under what authority*.
- **Vendor receipts are merchant-scoped.** A Stripe charge or a calendar invite confirms a transaction happened, but tells the principal nothing about which agent acted, why it chose that action, or what authority it held. They are scoped to one merchant, not to the human's whole agency surface.
- **There is no cryptographic binding** between an action, the agent that took it, and the human it represents. No portable artefact a third party — a regulator, an insurer, a downstream agent, or the human's own diary application — can independently verify or dispute with evidence.

As agents take more consequential actions under delegated authority, this gap becomes a public-safety, regulatory, and consumer-trust problem — and, under the EU AI Act and analogous regimes, a legal one. For delegation to be legible, the human needs a different artefact: a **per-action, cryptographically-signed, one-sentence-readable receipt, linked to the authority it was taken under**. That artefact is the Agency Receipt.

## 2. The Receipt Primitive

A receipt binds, in one signed object, the facts a human and a third party need to understand and dispute one agent action:

| Fact | Field(s) | Notes |
|---|---|---|
| **Who** acted, **for whom** | issuer `did:key`, principal | the agent and the human (or organisation) it represents |
| **What** was done, in one sentence | `human_summary` (+ `alt_summaries`) | readable without tooling, in the principal's preferred language |
| **The action**, structured | `action` (verb, category, parameters) | machine-readable description of the act |
| **The evidence** | `evidence` references | a chain that can substantiate the action under audit |
| **Under what authority** | `action.granted_by_receipt_id` / authority chain | links the action to a delegated-authority grant |
| **Bound and ordered** | Ed25519 `signature`, hash chain | signed over canonical JSON; chained to prior receipts |

The whole is signed with the issuing agent's Ed25519 key over a canonical encoding of the receipt. A receipt is therefore both immediately legible to a human and independently verifiable by a machine — neither property sacrificed for the other. The wire format is documented in [`SPEC.md`](spec/arp/0.1/spec.md) §3–§7.

ARP specifies the *shape* of a receipt when one is emitted. It does **not** specify *which* actions an agent must record — that is a runtime policy decision, and increasingly a regulatory one. ARP is domain-neutral: it applies to a refund-arbitration agent under SLA constraints, a procurement agent moving money, or a scheduling agent booking on a person's behalf, without forking.

## 3. Why a Receipt Is a Separate Primitive

The natural reaction to "agents act through tools and transports" is to assume those layers can also produce the human's record. The argument against that conflation:

- **MCP and A2A are plumbing, not accountability.** MCP integrates tools; A2A moves messages between agents. Neither produces a record the *represented human* can read, hold, and dispute. Folding the human-facing receipt into the tool or transport layer couples an accountability artefact to plumbing that has no reason to carry it.
- **The receipt outlives the action.** A tool call is ephemeral; the receipt is the durable record a regulator reads a year later or an insurer consults after a dispute. It must be portable across the runtime, the platform, and the transport — independent of all three.
- **One human, many agents and runtimes.** A person may be represented by agents on several stacks. A receipt format anchored to a single runtime cannot give that human one coherent, verifiable record of everything done in their name. The receipt is a primitive precisely because it is the common shape above heterogeneous runtimes.

So: the receipt is a primitive because it is human-facing, durable, and runtime-neutral — properties none of the layers beneath it provide.

## 4. Design Axioms

ARP is built on four axioms. They are not preferences; they are load-bearing for the receipt to compose with the rest of the portfolio.

### 4.1 Human-readable and machine-verifiable, at once

Every receipt resolves to one sentence a person can act on, and to bytes a verifier can check.

Consequence: the `human_summary` is a first-class, length-bounded field, not a derived afterthought — and the same object carries the structured `action`, evidence, and signature a machine needs. Neither audience is served by stripping the other.

### 4.2 Verifiable by anyone, offline

A receipt carries the issuer's `did:key`; verification needs only that and standard cryptography — no issuer service, no registry on the path.

Consequence: a regulator, insurer, or downstream agent that has never contacted the issuing runtime can confirm a receipt unforged. The human's record does not depend on the continued cooperation of the party that produced it.

### 4.3 Runtime- and transport-agnostic

The receipt shape is independent of the model, the hosting platform, and the underlying MCP/A2A plumbing.

Consequence: an agent on any stack emits the same receipt, and a single client can interpret a person's receipts across all of them. The format is the layer *above* tools and transport, not bound to either.

### 4.4 Records the shape, not the policy

ARP fixes what a receipt looks like; what *must* be receipted is left to the runtime and its jurisdiction.

Consequence: ARP stays domain-neutral and avoids encoding any one regulatory regime. Policy — which actions to record, under which law — lives with the deployer, where the legal obligation actually sits.

## 5. The Authority Chain

The distinctive structure ARP adds beyond a signed log is the **authority chain**. A receipt does not merely record *what* an agent did; it links to the grant of authority the action was taken *under* — via `action.granted_by_receipt_id` and the companion Delegated Authority Token sketch (`dat-companion.md`).

This is what makes a chain of agent actions auditable as *delegated* rather than merely *sequential*. When a human grants an agent authority to act within bounds, and that agent sub-delegates to another, each action references the receipt that authorized it. An auditor can walk from any action back to the human grant at the root — answering not just "what did the agent do" but "was it allowed to, and by whom." The authority chain is the structure that turns a pile of signed receipts into a defensible account of delegated agency.

## 6. Where This Fits

ARP is the **human-facing accountability layer above the tool and transport protocols**. MCP integrates tools; A2A moves messages; ARP records, for the human, the outcome an agent produced through them.

```
  +-----------------------------------------------------------+      +-----------------+
  |     sm-arp — Agency Receipts                              |      |                 |
  |     "agent X did Y for human Z, under authority A"        |      |  sm-conformance |
  |     signed · one-sentence-readable · authority-chained    |  ←   |                 |
  +-----------------------------------------------------------+      |  sm-arp defines |
  |     A2A (transport)  ·  MCP (tools)                       |      |  receipt vectors|
  |     the plumbing ARP records the outcome of               |      |  + criteria and |
  +-----------------------------------------------------------+      |  POINTS HERE for|
                                                                     |  its conformance|
                                                                     |  badge          |
                                                                     +-----------------+
```

**Conformance.** A runtime implementing ARP proves it by shipping a signed conformance badge. ARP owns its receipt vectors and conformance criteria; it **imports [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance)** for the badge envelope and verifier rather than minting its own (`conformance/arp/badge.py` pins the ARP corpus and signs through the primitive) — the badge mechanism is a shared substrate, and ARP is its first consumer in code, not only in prose.

## 7. Composition With Sister Primitives

| Producer | Output | Consumer |
|---|---|---|
| an agent runtime (any stack) | a signed ARP receipt of one action | the represented human's diary, a regulator, an insurer, a downstream agent |
| ARP receipts (chained) | a defensible account of delegated agency | audit and dispute resolution |
| a corpus of corroborated receipts | a recomputable `nanda-rep` score + `behavioral_merkle_root` (§8) | a registry's admission gate, an insurer, or a downstream agent deciding whom to trust |
| `sm-arp` conformance suite | receipt vectors + criteria | `sm-conformance`, which produces the runtime's badge |
| `sm-conformance` | a signed conformance badge | a registry admitting the ARP runtime |

A common deployment: an agent acts through MCP/A2A, emits an ARP receipt of the outcome, and ships a `sm-conformance` badge proving its ARP implementation is conformant. The human holds the receipts; a registry holds the badge.

## 8. Verifiable Reputation: From Receipts to Standing

A single receipt proves one action. The *aggregate* of an agent's receipts is something more valuable: the substrate for a portable, verifiable **reputation**. The Verifiable Receipts Profile (shipped as the `sm_arp.vrp` module) turns a receipt log into a standing any party can **recompute and verify offline**, with no trust in the agent's host.

**Commitment.** `behavioral_merkle_root` commits to an agent's receipts in order. A published score is bound to a specific receipt set — substitute or reorder the log and the root changes.

**Self-attested score (`nanda-rep/0.1`).** A category-weighted score over the agent's own valid receipts (`reputation_score`). It is honest about its weakness: an agent can inflate it by emitting receipts to itself, so 0.1 is a *baseline*, not a trust signal.

**Corroborated, collusion-resistant score (`nanda-rep/0.2`).** The load-bearing one. A receipt counts toward reputation only if the **counterparty co-signs it** (`cosign_receipt` → `evidence.witness_signatures`; `is_corroborated`). Uncorroborated receipts earn zero — standing cannot be manufactured by acting alone. On top of corroboration, the profile runs **collusion severance**: it builds the corroboration graph, finds dense mutually-co-signing rings (strongly-connected components weighted by internal density), and severs them, so a clique trading co-signs cannot farm reputation. `corroboration_rate` reports how much of a log is corroborated; `reputation_score_v2` is the gated, severed score.

**Attestation.** A credentialed authority (a registry or hosting community the resolver already trusts) signs the agent's published standing — binding identity, the ledger reference, and the behavioral root (`build_attestation` / `verify_attestation`, over `facts_digest`). A resolver can then rely on the standing **without trusting the agent's live server**: it verifies the signature, recomputes the score from the receipts, and confirms it matches.

The property that makes this *verifiable* reputation rather than asserted reputation: the score is a **pure function of the receipts**. A registry's admission gate, an insurer, or a downstream agent each recomputes it independently and gets the byte-identical value. Reputation becomes portable — it travels with the agent across communities — corroborated rather than self-claimed, collusion-resistant, and offline-verifiable. That is the difference between "this agent says it is reputable" and "anyone can check."

## 9. NANDA Alignment

[Project NANDA](https://projectnanda.org) defines four pillars the open Internet of Agents must solve: **DNS** (discovery), **CA** (decentralized identity), **Orchestration** (routing), and **Attestation** (verifiable evidence). ARP contributes verifiable, per-action, human-facing evidence of what agents do under delegated authority — complementing NANDA's per-*credential* primitives (AgentFacts describes what an agent *is*; KYA attests *who vouches* for it; an ARP receipt records what it *did* for a human).

> **Relationship to AAE — complementary.** The Attested Action Envelope (AAE), rendered by the operator surfaces, is also a per-action signed envelope. ARP and AAE are **complementary, not competing**: ARP is the *human-facing* receipt (one-sentence summary, authority chain, forward hash chain), AAE the *substrate* evidence record (four envelope kinds, bidirectional merkle-checkpoint audit). They compose through a defined seam — an ARP receipt's `evidence` references the AAE envelope(s) that substantiate the action, and an AAE `checkpoint` may cover ARP receipts, so ARP relies on AAE for reverse-audit anchoring rather than growing its own merkle layer. Neither is redundant: each owns what the other deliberately omits. The normative seam is `spec.md` §16.

## 10. Future Work

Items deferred from v0.1, in rough priority order:

1. **The Delegated Authority Token (DAT) companion**, promoted from sketch (`dat-companion.md`) to a normative spec the authority chain references.
2. **Richer action categories.** Sub-payload shapes for specific action classes (purchase, transfer, agreement), kept additive to the base receipt.
3. **A normative reputation profile.** The model in §8 ships as the `sm_arp.vrp` library; promote it to a published profile spec alongside the receipt spec, with its own conformance vectors.
4. **Resolving the ARP ↔ AAE relationship** (§9) — convergence, complement, or clean separation — ahead of v1.0.
5. **Published-spec governance** via `labs.stellarminds.ai/arp`, with the conformance registry operated alongside.

## 11. Related Packages

| Package | Role |
|---|---|
| [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) | The conformance substrate ARP points at for its badge |
| [`sm-locp`](https://github.com/Sharathvc23/sm-locp) | Open Compliance Protocol — what an agent is *permitted* to do; ARP records what it *did* |
| [`sm-attest-viewer`](https://github.com/Sharathvc23/sm-attest-viewer) | Renderer for AAE action-envelope chains (complementary to ARP — see §8) |

---

*First published: 2026-05-31 | Last modified: 2026-06-14*

*Personal research contributions aligned with [Project NANDA](https://projectnanda.org) standards. [Stellarminds.ai](https://stellarminds.ai)*
