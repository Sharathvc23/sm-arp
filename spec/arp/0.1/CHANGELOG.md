# ARP Changelog

The wire identifier is `arp/0.1` and, per `governance.md` §1 ("Versioning"), remains a
fluid working draft until v0.1 RC: changes accumulate here against the latest `main`.

## v0.1.1 — detached witness evidence (audit 2026-11)

Driven by the 2026-11 audit of the reference implementation and its consumers
(sm-oversight quorum, VRP corroboration). No existing vector's signature or chain link
changed: every receipt an issuer emits has no witnesses yet, and for those the new rule
is byte-for-byte the old one.

- **§5.1 (new), §6.1, §6.3, §6.4 — `evidence.witness_signatures` is detached evidence.**
  It is excluded from the canonical string the issuer signs, from the hash-chain link,
  and from the bytes a witness signs — one rule for all three. Previously §6.1 excluded
  only `signature`, so a witness co-signature appended after issuance (which is the
  only time one can be appended) invalidated the issuer's signature and moved the chain
  link; the VRP corroboration payload and sm-oversight's quorum bytes already used the
  detached rule, so three commitments over the "same" receipt disagreed.
- **§5.1 — `signer_did` is an accepted read alias for `witness_did`.** Writers emit
  `witness_did`; readers accept both, `witness_did` governing when both are present.
- **§4.5 — the authority chain authenticates the grant.** Verifiers MUST verify the
  grant receipt's own signature, require the resolved receipt's `receipt_id` to equal
  `granted_by_receipt_id`, require a present, non-empty `granted_to_did` equal to the
  action's `issuer_did`, require a present RFC 3339 `grant_expires_at` compared as an
  instant (not a string), and require `granted_scope` to be a non-empty array. Formerly
  the checks were relationship-only.
- **§3 — unknown top-level members.** Clarified that the known set is exactly §3.1 +
  §3.2, that the schema enforces it, and that the reference strict verifier does too.
- **Vectors:** `23-witnessed-receipt` (witnesses appended after issuance; issuer
  signature verifies; counterparty corroborates), `24-witness-tampered` (tampered
  co-signature: issuer signature still verifies, corroboration fails),
  `25-unknown-top-level-member` (strict verifiers reject). 22 → 25 vectors.

## v0.1.0 — Initial public release

First public release of the Agency Receipt Protocol.

- **Receipt envelope** — required and optional members, signed over RFC 8785 JCS
  with Ed25519; verifiable by anyone holding the issuer's `did:key`.
- **Action object** with normative categories plus `other`.
- **Evidence, jurisdiction, accessibility, authority chain** sub-objects.
- **Hash-chain semantics** for ordering and linking receipts.
- **22 language-agnostic receipt vectors** plus a framework-agnostic Python
  conformance harness (`conformance/arp/`).
- The signed conformance badge is produced by
  [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance); ARP points
  at it rather than defining its own.
