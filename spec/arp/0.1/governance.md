# ARP — Governance and Stewardship

**Status:** Working Draft, v0.1.
**Last edited:** 2026-05-31.

## What this document covers

This document defines:

1. How changes to the ARP specification are proposed, reviewed, and ratified.
2. Who can publish a "conformant ARP implementation" claim.
3. The path for ARP to move from working draft to a published standard.
4. The contributor norms, trademark policy, and security-disclosure process.

It is not normative for the wire protocol itself — see [`spec.md`](./spec.md) for
that. This document is normative for *how the spec is governed*.

## 1. Change process

Changes to `spec.md` are proposed via pull request:

1. Open a PR that updates the spec, the JSON Schemas, and the vectors
   **together**. Drift between these is a defect.
2. The PR description **MUST** include a "Why this is a wire-protocol change"
   section explaining the impact on existing receipts and implementers.
3. CI runs the conformance suite. PRs that break existing vectors must either
   (a) update the affected vectors with rationale, or (b) be rejected.
4. Maintainer review (see `CODEOWNERS`) approves before merge.

### Versioning

Until v0.1 RC, the wire-protocol identifier remains `arp/0.1` and is treated as a
fluid working draft; implementations track the latest commit on `main`. At v0.1
RC the wire identifier is frozen: subsequent breaking changes get a new minor
(`arp/0.2`); backward-compatible additions remain on `arp/0.1` and accumulate in
[`CHANGELOG.md`](./CHANGELOG.md).

## 2. Implementation conformance claims

A project **MAY** claim "conformant ARP v0.1 implementation" if:

1. It emits receipts that pass every positive vector in `vectors/arp/0.1/` when
   run through `conformance/arp/test_arp_v01.py`.
2. It rejects every negative vector at the documented expected stage.
3. It documents its mode (strict vs tolerant; see `spec.md` §12.2) clearly.

The claim is reputational: a project that publicly asserts conformance and is
shown to fail the suite is noted on the spec's bug tracker.

A formal conformance program runs at **labs.stellarminds.ai/conformance**. Per
[`conformance.md`](./conformance.md), a conformant runtime ships a signed
[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) badge, and
registry admission requires lab re-run, counter-signature, or attested CI —
a self-signed badge alone is not sufficient.

## 3. Path to a published standard

ARP is **published-spec-first**: this MIT-licensed repository is the canonical
source of truth, and `labs.stellarminds.ai/arp` resolves to it. No external
standards-body submission is planned for v0.1.

| Stage | Milestone |
|---|---|
| **Working draft** (now) | v0.1 spec + schemas + 22 receipt vectors + conformance harness |
| **Public publication** | `labs.stellarminds.ai/arp` resolves here; the conformance registry accepts external submissions |
| **Adoption** | Independent agent runtimes implement ARP, pass the conformance program, appear in the registry |

Why published-spec-first rather than submission to an external standards body for
v0.1: adoption credibility comes from real implementations and a conformance
suite, not from third-party endorsement. The open-standard pattern works without
ceding control — Stripe's Idempotency-Key and the AWS S3 API are de facto
standards via adoption, not via blessing.

## 4. Trademark and the conformance Mark

"ARP", "Agency Receipt Protocol", and the conformance program's badge graphic are
**Stellarminds-controlled** marks. The mark-use policy is published at
`labs.stellarminds.ai/conformance/mark-policy` and is enforced by the conformance
registry — runtimes that pass the program receive the right to display the mark;
runtimes that have not been admitted (or whose badge has been revoked) may not.

The wire identifier `arp/X.Y` is purely a string and not a trademark claim —
implementations producing receipts with this version field are simply
implementing the published specification. Mark use covers the **certification
claim**, not the protocol itself.

## 5. Contributor licensing

Contributions are accepted under a Developer Certificate of Origin (DCO) sign-off
model; see [`CONTRIBUTING.md`](../../CONTRIBUTING.md). The spec and schemas are
released under the MIT License (see `LICENSE`).

## 6. Security disclosure

Vulnerabilities in the spec (cryptographic weaknesses, ambiguous canonicalization,
side-channel risks) should be reported per `SECURITY.md` with `[security] arp` in
the subject, under a 90-day coordinated-disclosure default.

## 7. What is not in scope for this document

- **Operational concerns of running an Issuer Log or Agency Log service.** Those
  are implementation details for individual deployments.
- **Pricing or commercial terms of any specific ARP implementation.** This is
  open-standard governance; commercial decisions sit with implementers.
- **Legal interpretation of jurisdictional fields.** The spec defines the data
  structure; legal interpretation is for downstream tools and counsel.

[labs.stellarminds.ai/arp]: https://labs.stellarminds.ai/arp
