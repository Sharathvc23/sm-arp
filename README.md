# sm-arp — Agency Receipt Protocol

The portable, cryptographically signed receipt format AI agents emit when
they act on behalf of humans. Runtime-agnostic, vendor-neutral, MIT-licensed.

ARP sits above MCP (tool integration) and A2A (agent-to-agent transport)
— the **human ↔ agent accountability layer** those standards deliberately
do not address.

## Status

- **[WHITEPAPER.md](./WHITEPAPER.md)** — motivation, design choices, and how ARP fits the portfolio.
- **[spec/arp/0.1/spec.md](./spec/arp/0.1/spec.md)** — the canonical normative document (RFC-style).

## Use it as a library

ARP ships one canonical Python implementation, `sm_arp`, so every runtime
imports the *same* build/sign/verify/store code instead of vendoring its own — the
receipt envelope cannot drift between them. The library needs nothing but
`cryptography`, `base58`, and `jcs`.

```python
from sm_arp import Identity, build_action, issue_receipt, verify_receipt, IssuerLog

me = Identity.generate()
r = issue_receipt(me, principal_did=me.did,
                  action=build_action(category="data_shared", human_summary="shared my calendar"))
assert verify_receipt(r).ok                 # structure → signature → authority → hash chain
IssuerLog("log.sqlite").append(r)           # SQLite Issuer/Agency Log, hash-chained per issuer
```

`sm_arp`'s verifier is tested against the canonical 22-vector corpus and asserted
byte-for-byte equal to the conformance harness's verdict on every vector — so the
library and the spec cannot disagree.

## Layout

- `sm_arp/` — the consumable library: `identity` (Ed25519 + did:key), `receipts` (build/sign/verify/canonical/chain), `store` (SQLite Issuer/Agency Log).
- `arp_cli/` — the `arp` command-line tool (`pip install 'sm-arp[cli]'`).
- `WHITEPAPER.md` — design rationale and portfolio positioning.
- `spec/arp/0.1/spec.md` — the canonical normative receipt spec (RFC-style).
- `spec/arp/0.1/conformance.md` — ARP conformance criteria; points at `sm-conformance` for the badge.
- `spec/arp/0.1/governance.md` — stewardship and the path to public publication.
- `spec/arp/0.1/dat-companion.md` — the Delegated Authority Token sketch the authority chain references.
- `schema/arp/0.1/` — JSON Schemas (Draft 2020-12) for the receipt envelope.
- `vectors/arp/0.1/` — 22 language-agnostic receipt vectors.
- `conformance/arp/` — framework-agnostic Python conformance harness for receipts.

## The conformance badge lives in sm-conformance

ARP owns *what a conformant runtime must do* (this repo) and the receipt vectors
it is tested against. It does **not** own the signed-badge mechanism — that is a
generic, protocol-neutral substrate that lives in its own primitive,
[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance). ARP is its
first consumer.

## How to claim ARP compliance

1. Implement the spec in your runtime.
2. Run `pytest conformance/` against the bundled vectors. Every positive vector
   MUST pass; every negative vector MUST be rejected at the documented stage.
3. Produce a signed conformance badge with
   [`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) and ship it
   at your runtime's `.nanda/conformance.json` — and, if you serve it over HTTP,
   at the canonical `/.well-known/conformance.json` (see sm-conformance SPEC §3.2).

The badge is self-signed and independently re-verifiable: anyone can recompute
`pytest conformance/` against the bundled vectors and check the signature offline.

## Implementing ARP

ARP is runtime-agnostic — any agent stack can emit conformant receipts. Implement
the spec, pass `conformance/`, and ship a signed
[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) badge. The
receipt format depends on nothing but Ed25519, JCS, and the W3C `did:key` method.

## License

MIT — see [LICENSE](./LICENSE).
