# Contributing to ARP

Contributions are accepted under the Developer Certificate of Origin (DCO)
sign-off model. Add `Signed-off-by: Your Name <you@example.com>` to every
commit (`git commit -s`).

## Change process

1. Open a PR that updates the spec, the JSON Schemas, the vectors, and any
   affected conformance code **together**. Drift between these is a defect.
2. The PR description MUST include a "Why this is a wire-protocol change"
   section explaining the change's impact on existing receipts and badges.
3. CI runs the conformance suite. PRs that break existing vectors must either
   (a) update the affected vectors with rationale or (b) be rejected.
4. Two maintainer reviews required before merge.

## What goes here vs. the reference implementations

- Spec text, schemas, vectors, conformance harness, badge program — here.
- Concrete agent runtimes that implement ARP — in their own repos. They link
  back here for the spec and bundle this package via
  `pip install sm-arp` for the conformance harness.

See `spec/arp/0.1/governance.md` for the full governance model.
