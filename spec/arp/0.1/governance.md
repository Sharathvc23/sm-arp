# ARP — Governance and Stewardship

**Status:** Working Draft, v0.1.
**Last edited:** 2026-05-31.

## What this document covers

This document defines:

1. How changes to the ARP specification are proposed, reviewed, and ratified.
2. Who can publish a "conformant ARP implementation" claim.
3. The intended path for ARP to move from its current incubation home into an independent standards-body home.
4. The contributor norms that apply during the incubation period.

It is not normative for the wire protocol itself — see [`spec.md`](./spec.md) for that. This document is normative for *how the spec is governed*.

## 1. Incubation phase (now → v0.1 RC)

### 1.1 Home

ARP v0.1 is incubated inside the NANDA Chapter Protocol repository under `spec/arp/`. This is a deliberate, time-bounded choice: incubation lets the spec coexist with a working reference implementation that exercises every primitive end-to-end. A spec that has never been implemented is a spec full of unknowable bugs.

### 1.2 Change process

During incubation, changes to `spec/arp/0.1/spec.md` are proposed via the parent repository's normal pull-request workflow:

1. Open a PR that updates the spec, the JSON Schemas, the vectors, and the reference implementation **together**. Drift between these is a defect.
2. The PR description **MUST** include a "Why this is a wire-protocol change" section explaining the change's impact on existing receipts and implementers.
3. CI runs the conformance suite. PRs that break existing vectors must either (a) update the affected vectors with rationale or (b) be rejected.
4. Two reviewers from the core contributors (see §1.4) approve before merge.

### 1.3 Versioning during incubation

Until v0.1 RC, the wire-protocol identifier remains `arp/0.1` and is treated as a fluid working draft. Implementations are expected to track the latest commit on the main branch.

At v0.1 RC (release candidate), the wire identifier is frozen. Subsequent breaking changes get a new minor version (`arp/0.2`); subsequent backward-compatible additions remain on `arp/0.1` but accumulate in `CHANGELOG.md`.

### 1.4 Core contributors

Incubation-phase core contributors are a small group with the merge authority described in §1.2. The list is published in [`CONTRIBUTORS.md`](./CONTRIBUTORS.md) at the standalone repo creation time. During the current incubation period inside this repository, the maintainer set is the repository's `CODEOWNERS` file (see repository root).

Joining the core contributors during incubation requires a substantive contribution — a schema change with vectors, a security-considerations addition with rationale, or a reference-implementation feature — accompanied by a sponsorship from an existing core contributor.

## 2. Implementation conformance claims

A project **MAY** claim "conformant ARP v0.1 implementation" if:

1. It emits receipts that pass every positive vector in `vectors/arp/0.1/` when run through `conformance/arp/test_arp_v01.py`.
2. It rejects every negative vector at the documented expected stage.
3. It documents its mode (strict vs tolerant; see spec §12.2) clearly in its README or equivalent.

There is no certifying body in incubation. The claim is reputational: a project that publicly asserts conformance and is shown to fail the suite is publicly noted on the spec's bug tracker.

A formal conformance program is being launched at **labs.stellarminds.ai/conformance** alongside the standalone repo extraction (§3). Per [`conformance.md`](./conformance.md) §11, registry admission requires lab re-run, counter-signature, or attested CI — self-signed badges alone are not sufficient.

## 3. Path to a published standard

ARP is **published-spec-first**: the canonical spec is incubated inside this umbrella repository alongside its first reference implementation, then extracted to a standalone MIT-licensed repository at `Sharathvc23/arp-spec`, then published externally via [labs.stellarminds.ai/arp]. No external standards-body submission is planned for v0.1.

The path:

| Stage | Milestone | Criteria |
|---|---|---|
| **Incubation** (now) | v0.1 working draft + reference implementation + conformance program v0.1 (badge spec, vectors, three signed runtime badges) | Internal review, design-partner feedback |
| **Standalone repo** | v0.1 published in standalone `arp-spec` repository under MIT license | Per [`EXTRACTION.md`](../EXTRACTION.md): the umbrella's `spec/arp/`, `schema/arp/`, `vectors/arp/`, and the badge program become the new repo's source of truth |
| **Public publication** | `labs.stellarminds.ai/arp` resolves to the public spec; conformance registry at `labs.stellarminds.ai/conformance` accepts external submissions | Mark policy ratified; lab-rerun infrastructure operational |
| **Adoption** | Other agent runtimes implement ARP, pass the conformance program, appear in the registry | Multiple independent implementations badged |

Why published-spec-first rather than submission to an external standards body for v0.1: with ~300 members on the live federation and a working reference implementation, adoption credibility comes from real production use, not from third-party endorsement. The open-core pattern works without ceding control of the standard — Stripe Idempotency-Key, AWS S3 API are de facto standards via adoption, not blessing.

The reference implementation in `chapter/`, `member-sdk/`, etc. continues to live in this umbrella regardless of where the canonical spec lives.

## 4. Trademark and the conformance Mark

"ARP", "Agency Receipt Protocol", and the conformance program's badge graphic are **Stellarminds-controlled** marks. The mark-use policy is published at `labs.stellarminds.ai/conformance/mark-policy` and is enforced by the conformance registry — runtimes that pass the program receive the right to display the mark; runtimes that have not been admitted (or whose badge has been revoked) may not.

The wire identifier `arp/X.Y` is purely a string and not a trademark claim — implementations producing receipts with this version field are simply implementing the published specification. Mark use covers the **certification claim**, not the protocol itself.

## 5. Contributor licensing

During incubation, contributions to `spec/arp/0.1/` and the reference implementation are under the parent repository's existing contribution terms (see `LICENSE` at the repository root). At the standalone-repo creation, contributions will be under a Developer Certificate of Origin (DCO) sign-off model documented in `CONTRIBUTING.md` at the standalone repo.

## 6. Security disclosure

Vulnerabilities in the spec (cryptographic weaknesses, ambiguous canonicalization, side-channel risks) should be reported to the same `SECURITY.md` contact as the parent repository. Vulnerabilities in the reference implementation should be reported via the same path with `[security] arp-impl` in the subject.

After standalone-repo creation, ARP will publish its own `SECURITY.md` with a dedicated disclosure address and the standard 90-day coordinated-disclosure default.

## 7. What is not in scope for this document

- **Operational concerns of running an Issuer Log or Agency Log service.** Those are implementation details for individual deployments.
- **Pricing or commercial terms of any specific ARP implementation.** This is open standards governance; commercial decisions sit with the implementers.
- **Legal interpretation of jurisdictional fields.** The spec defines the data structure; legal interpretation is for downstream tools and counsel.

[labs.stellarminds.ai/arp]: https://labs.stellarminds.ai/arp
