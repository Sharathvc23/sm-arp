# Threat Model — sm-arp (Agency Receipt Protocol)

This document states what an ARP **receipt** does and does not prove, the adversaries it
defends against, and the residual risks a verifier / relying party (RP) must handle
itself. It complements `spec/arp/0.1/spec.md` (normative) and shares its cryptographic
substrate with [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) — see
that repo's `THREATMODEL.md` for the substrate-level threats (canonicalization, key
custody) that apply here too.

## 1. The organizing idea

A receipt binds an **action-claim to the issuing agent's key** — not to the principal's
consent and not to reality. A valid signature proves only:

> "the agent holding key `issuer_did` asserts that, at `issued_at`, it took `action` on
> behalf of `principal_did`, under the authority in `authority_chain`."

It is the **agent's** signed statement about its own behaviour. In v0.1 it proves the
agent *said so*; it does **not** prove the principal authorized it, that the authority
covered this action, or that the action actually happened at the counterparty. **Every
threat below is the gap between "agent `A` signed 'I acted for `P` under authority `X`'"
and "`P` actually authorized `A` to do `X`."**

## 2. Assets, trusted base, trust boundaries

**Assets**
- Integrity of the action-claim (who did what, for whom, when, under what authority).
- The **agent ↔ principal delegation binding** (the accountability link).
- Tamper-evidence and ordering of an issuer's history (the hash chain / Agency Log).
- The relying party's decision to *act on*, *audit*, or *dispute* a receipt.

**Trusted computing base (TCB)** — security reduces to:
- Ed25519, **JCS canonicalization** (RFC 8785), the JSON Schema validators, and `did:key`
  resolution — *identical substrate to `sm-conformance`* ("byte-for-byte equal to the
  conformance harness's verdict"). Its substrate threats apply unchanged.
- The integrity and completeness of the **issuer log** that the hash chain is checked
  against, and of the verifier's **replay seen-set**.

**Trust boundary:** the signature covers the canonical receipt minus `signature`. Fields
the verifier reads but does **not** cryptographically tie to a third party — notably
`principal_did`, `authority_chain` (descriptive in v0.1), and `jurisdiction`
(self-asserted, never validated) — are only as trustworthy as the issuing agent. The
agent is *inside* the trust boundary for everything it asserts about *others*.

## 3. Adversaries

- **Dishonest / compromised issuing agent** — the primary adversary: it holds the signing
  key and authors the receipt, so it can assert anything about the principal, authority,
  and jurisdiction. Most threats below are this actor.
- **Replayer / relay** — re-presents a valid receipt to trigger or claim an action twice.
- **Repudiating principal** — later denies having authorized an action.
- **Under-checking consumer** — an RP that verifies the signature and stops there.

## 4. Threats

| # | Attack | Defended by | Residual risk |
|---|---|---|---|
| **A1** | **Unverified delegation / principal impersonation.** The agent signs; `principal_did` is just a string it asserts. In v0.1 `authority_chain` is **descriptive only** and principal-binding is `SHOULD` (§6.3.8–9, §7). | `SHOULD` resolve principal↔issuer binding via a DAT grant or platform ledger; `consent_evidence_hash` | **the v0.1 headline gap:** a base verifier accepts a receipt naming *any* principal. Authority is *noted, not evaluated*. Closed at **rung-2 / v0.2** (DAT). |
| **A2** | **Scope escalation.** Authority exists but doesn't cover *this* action category/amount (a "read calendar" grant used to "send email"). | §6.3.9 "covers the action category" — but only "when the DAT spec is in scope" (v0.2) | v0.1 cannot enforce scope; until DAT, scope is unchecked |
| **A3** | **Replay / double-execution.** A valid receipt re-presented to make an action (esp. `payment_*`) count twice. | the spec **mandates** a stateful guard — a bounded `(issuer_did, receipt_id)` seen-set with **TTL ≥ 600 s** (§ "Replay") — plus the ±300 s `issued_at` window and the per-issuer hash chain | the seen-set is **TTL-bounded**: a receipt replayed *after* the TTL expires escapes it. Durable single-use for high-value actions needs a **persistent** ledger, not just the in-memory TTL set. |
| **A4** | **Stale / forward-dated receipt.** Present an old (or future-stamped) receipt as current. | `issued_at` **MUST** be within ±300 s (rejects stale *and* future — clock-skew built in, §3.3) | the ±300 s window means **archival** verification falls outside it; long-term trust shifts to the hash chain + log, not the timestamp |
| **A5** | **Issuer-log fork / equivocation / omission.** The issuer controls its own log: maintain divergent chains for different audiences, drop an inconvenient receipt, or rewrite history. | per-issuer SHA-256 hash chain over JCS bytes **incl. signature** (§6.4); "presence-without-validity is a stronger failure than absence" | the chain is tamper-**evident**, not tamper-**proof** — fork/gap detection needs an external monitor; **no cross-issuer ordering**. Closed at **rung-3** (witnessed log). |
| **A6** | **Principal repudiation.** Principal claims "I never authorized this." | `consent_evidence_hash`; principal-signed DAT grants (v0.2) | v0.1 accountability is **one-sided** (agent-attested) — the principal never signs, so neither side is provable |
| **A7** | **Jurisdiction misstatement.** Issuer understates to dodge a regime (or overstates). | spec's conservative-omit posture (§8.3); `consent_evidence_hash` | "Verifiers do **not** validate" `jurisdiction`/`applicable_regimes` (§8.1) — it is issuer-asserted **evidence**, not a verified fact |
| **A8** | **Principal privacy / linkability.** A stable `did:key` principal + portable receipts + per-issuer chains let a third party correlate and deanonymize a *human's* behaviour; receipts also carry residence + action summaries (PII). | data minimization; pseudonymous identity-of-record; selective disclosure | inherent to a portable signed record *about a human* — consider rotating principal identifiers and redaction on presentation |
| **A9** | **Key compromise / rotation of the issuing agent.** Leaked issuer seed → forge receipts as `A`; post-rotation, old-key receipts stay valid in their window. | custody discipline; rotate; RP tracks issuer **key history** | **no in-protocol revocation** — RPs must choose a grandfathering policy; revocation lives at the platform / DAT layer (cf. `sm-conformance` T6) |
| **A10** | **Canonicalization / substrate divergence.** Two implementations canonicalize differently → a receipt (and its chain hash) verifies-and-means differently. | shared cross-language JCS vectors; strict schema; chain hash over JCS bytes incl. signature | every new language port is new TCB surface (cf. `sm-conformance` T8) |

## 5. Explicit non-goals (v0.1)

- **Evaluating the authority grant** — `authority_chain` is descriptive until the DAT spec
  lands (v0.2). Stated, not hidden.
- **Proving the action occurred** at the counterparty — a receipt is the *agent's* claim;
  pair it with `evidence` (§5) and out-of-band vendor receipts for ground truth.
- **Mandating which actions must be recorded** — that is runtime/regulatory policy, not ARP.
- **Confidentiality** — receipts are portable, presentable, and not encrypted by the format.
- **Cross-issuer global ordering / non-equivocation** — absent an external witnessed log.

## 6. Trust rungs (and the roadmap)

ARP is an explicit ladder; naming the rungs makes A1/A5 deliberate roadmap items rather
than open holes:

- **Rung 1 — agent self-attestation (v0.1 base).** The agent signs its own receipt. Proves
  the agent's statement; principal consent and authority are *asserted, not verified*.
- **Rung 2 — verified delegation (DAT, v0.2).** Principal-signed **Delegated Authority
  Tokens** (see `spec/arp/0.1/dat-companion.md`) that verifiers evaluate for validity,
  non-revocation, and **scope coverage** — binding principal consent and closing
  A1/A2/A6.
- **Rung 3 — witnessed Agency Log.** An external append-only / transparency witness over
  issuer chains detects forks, gaps, and equivocation — closing A5. (Same shape as
  `sm-conformance`'s rung-3 transparency log.)

## 7. Relying-party / verifier checklist

Steps 1–4 are the normative `MUST` of §6.3; 5–10 are where most RPs under-reach.

1. **Schema** (strict; reject unknown top-level members) and `version == "arp/0.1"`.
2. **Verify signature:** resolve `issuer_did` → public key, recompute JCS canonical `C`,
   verify Ed25519. Reject on failure.
3. **Freshness window:** require `issued_at` within the accept window (default ±300 s) —
   this rejects stale *and* forward-dated receipts (A4). Tune per deployment.
4. **Hash chain:** if `previous_receipt_hash` is present, fetch the prior receipt by
   `receipt_id` from the issuer log and verify the SHA-256 over its canonical bytes
   *including its signature*; treat presence-without-validity as a hard fail (A5).
5. **Replay guard (normative):** maintain the spec-mandated bounded `(issuer_did,
   receipt_id)` seen-set (TTL ≥ 600 s) and reject duplicates; for high-value actions
   (`payment_*`), back it with a **persistent** ledger so single-use survives beyond the
   TTL (A3).
6. **Resolve the principal binding out of band** (DAT grant / platform ledger) — do **not**
   trust `principal_did` on the agent's word alone (A1).
7. **Evaluate `authority_chain`:** unrevoked, and **covers the action category and scope**.
   Mandatory once DAT/v0.2 is in scope; until then, treat authority as *unproven*, not
   *granted* (A2/A6).
8. **Track issuer key history** and choose a grandfathering policy across rotation (A9).
9. Treat `jurisdiction` / `applicable_regimes` as issuer-asserted **evidence** — cross-check
   downstream; never rely on it as validated (A7).
10. **Minimize principal PII** when archiving or presenting receipts (A8).
