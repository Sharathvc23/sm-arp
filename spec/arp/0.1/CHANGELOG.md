# ARP Changelog

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
