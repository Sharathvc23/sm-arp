# ARP Conformance — v0.1

**Status:** Working Draft.
**Last edited:** 2026-05-31.

> **Source of truth.** ARP owns *what an ARP runtime must do to be conformant*
> (this document) and the receipt vectors it is tested against
> (`vectors/arp/0.1/`). It does **not** own the conformance-badge mechanism —
> that is specified by **[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance)**,
> the substrate every Stellarminds primitive shares. ARP is its first consumer.

---

## 1. What conformance means for ARP

A runtime that claims to implement ARP must prove two things:

1. **It speaks the protocol.** Its receipts conform to the ARP receipt spec.
2. **That proof is portable.** It ships a signed, offline-verifiable badge that
   any party can re-check without trusting a service.

ARP defines (1). The badge in (2) is defined by `sm-conformance`. This split is
deliberate: the badge envelope — signing, canonical encoding, `suite_digest`
pinning, the verification algorithm, and the self → lab → CI trust ladder — is a
generic mechanism with no ARP-specific content, so it lives in its own primitive
rather than inside this spec. Re-specifying it here would fork a shared standard.

## 2. ARP conformance criteria

A **conformant ARP runtime** is one that:

1. Emits receipts whose serialized form passes the JSON Schemas in
   `schema/arp/0.1/`.
2. Computes signatures per `spec.md` §6 such that every positive vector in
   `vectors/arp/0.1/` verifies.
3. Rejects every negative vector in `vectors/arp/0.1/` at the documented stage
   (schema, signature, hash chain, etc.).

The ARP conformance suite is `conformance/arp/` — it loads the vectors and
checks a runtime against (1)–(3). It is framework-agnostic: no NANDA-specific
code paths are exercised.

## 3. The conformance badge

A conformant ARP runtime ships a **conformance badge** — the signed
`.nanda/conformance.json` envelope specified by
[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) (see its
`SPEC.md`). The badge records the run of the ARP conformance suite: which
runtime, which protocol versions (including the ARP version), the
`suite_digest` over the vector corpus, and the pass/fail counts.

- **Envelope, signing, canonical encoding, suite digest, verification
  algorithm, verifier exit codes** — all per `sm-conformance/SPEC.md`. This
  document adds nothing to them.
- **Badge vectors** (`valid-signed-badge`, `tampered-payload`, … the negative
  cases) are owned by `sm-conformance`, not ARP.
- **What a badge does and does not prove** is per `sm-conformance/SPEC.md` §3 and
  the trust ladder in §11 — summarized in §4 below for the ARP Mark.
- **Producing the badge** is a thin call into the primitive: `conformance.arp.badge`
  (install the `conformance` extra) pins the ARP vector corpus and signs the envelope
  via `sm-conformance`. ARP imports the primitive rather than re-implementing it —
  it is sm-conformance's first consumer in code, not only in prose.

## 4. The ARP Conformance Mark

A self-signed badge proves authorship and asserts a claim; it does **not**
establish that the run happened or that the counts are accurate (per
`sm-conformance/SPEC.md` §3). A system that admits, certifies, or registers an
ARP runtime under the **ARP Conformance Mark** **MUST** establish at least one
of the trust-ladder rungs defined in `sm-conformance/SPEC.md` §11 — independent
re-run, counter-signature, or attested CI.

Publishing an admission under the ARP Conformance Mark on the basis of a bare
self-signed badge is **prohibited**. The Mark is operated at
`labs.stellarminds.ai/conformance`.

## 5. References

- `spec.md` (this directory) — the ARP receipt the runtime emits.
- [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) — the badge
  envelope, signer, verifier, trust ladder, and badge vectors.
- `spec/0.2/did-key.md` — `did:key` derivation used by the badge's `signed_by`.
