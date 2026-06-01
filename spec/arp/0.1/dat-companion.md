# DAT — Delegated Authority Token (companion sketch)

> **Status: DRAFT / SKETCH. NOT NORMATIVE in v0.1.** This document outlines the companion spec that ARP v0.1 references via its `authority_chain` field. DAT will be normalized in ARP v0.2; for now this sketch is purely descriptive.

## Purpose

ARP records *what an agent did*. DAT records *what an agent was allowed to do*. Together they answer the two halves of every accountability question: "did this happen?" (ARP) and "was it authorized?" (DAT).

DAT defines a portable, cryptographically signed grant from a principal (human or organisation) to an issuer (agent) authorizing a bounded category of actions for a bounded period under bounded conditions.

## Envelope sketch

```json
{
  "version": "dat/0.1",
  "grant_id": "dat:did:key:z6Mki...:movies-budget-grant-q2",
  "grantor_did": "did:key:z6Mki...",
  "grantee_did": "did:key:z6Mktw...",
  "issued_at": "2026-04-01T00:00:00Z",
  "not_before": "2026-04-01T00:00:00Z",
  "not_after":  "2026-06-30T23:59:59Z",
  "scope": {
    "action_categories": ["purchase"],
    "constraints": {
      "amount_currency": "USD",
      "amount_cents_per_action_max": 5000,
      "amount_cents_per_period_max": 50000,
      "period": "month",
      "counterparty_allowlist": [
        "domain:amctheatres.com",
        "domain:fandango.com",
        "merchant_category:7832"
      ],
      "jurisdictions": ["US-MA", "US-NY"]
    }
  },
  "revocation": {
    "revocable_by": ["grantor", "grantor.guardian"],
    "revocation_lookup_uri": "https://issuer.example/dat/revocations"
  },
  "signature": "..."
}
```

## Key properties

- **Scoped.** A DAT names specific action categories the grantee may invoke, with constraints (amount caps, counterparty allowlists, jurisdictional limits, conditional triggers).
- **Bounded.** Every DAT has `not_before` and `not_after`. A grantee using an expired DAT in an ARP receipt's `authority_chain` is a verification failure.
- **Revocable.** A grantor can revoke a DAT before its `not_after`. Verifiers check a revocation list at verification time.
- **Composable.** Multiple DATs can co-authorize an action; the receipt's `authority_chain` lists each grant ID. The action must satisfy *every* listed grant's constraints, not just one.
- **Signed by the grantor's own key.** DATs are signed by the principal, not the agent. This is the key distinction from ARP, where the agent signs.

## Open questions for v0.2 normalization

1. **Hierarchical grants.** Should a DAT be able to grant another DAT (sub-delegation)? Probably yes, with a chain depth limit. Each link in the chain logs in `authority_chain`.
2. **Revocation cost.** A revocation list per issuer is the simple model; a CRL-like distributed revocation is harder but more scalable. v0.2 should specify the minimum-viable approach.
3. **Scope language.** The `constraints` object above is illustrative. Real specification needs a grammar: arithmetic on amounts, set membership on counterparties, time-window predicates. CEL (Common Expression Language) is a candidate.
4. **Human-readable summary.** A DAT, like a receipt, needs a `human_summary` so the principal can review what they signed. Likely a required field in v0.2.
5. **Integration with WebAuthn / Passkey.** Real-world grants from humans likely come via passkey-attested actions, not raw signature. The DAT envelope should record the underlying authentication ceremony.
6. **Standing authority.** What represents the "initial bind" between principal and agent when no explicit DAT exists? Probably an implicit `dat:initial-bind` grant recorded at registration time.

## Why this is a separate spec

DAT is large enough — and adjacent enough to existing identity standards (OAuth scopes, WebAuthn, did:key, verifiable credentials) — to deserve its own document and its own conformance suite. Bundling it inside ARP would make ARP too sprawling.

The intent is: DAT v0.1-draft sketched here → DAT v0.1 published parallel to ARP v0.2 → DAT v1.0 and ARP v1.0 published in lockstep via labs.stellarminds.ai.

---

This sketch is intentionally not normative. Comments welcome; specification work begins after ARP v0.1 stabilizes.
