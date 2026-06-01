# sm-arp — Agency Receipt Protocol

The portable, cryptographically signed receipt format AI agents emit when
they act on behalf of humans. Runtime-agnostic, vendor-neutral, MIT-licensed.

ARP sits above MCP (tool integration) and A2A (agent-to-agent transport)
— the **human ↔ agent accountability layer** those standards deliberately
do not address.

## Status

Working Draft v0.1, May 2026. Published-spec-first via
[labs.stellarminds.ai/arp](https://labs.stellarminds.ai/arp).

- **[WHITEPAPER.md](./WHITEPAPER.md)** — motivation, design choices, and how ARP fits the portfolio.
- **[spec/arp/0.1/spec.md](./spec/arp/0.1/spec.md)** — the canonical normative document (RFC-style).

## Layout

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
   at your runtime's `.nanda/conformance.json`.
4. Submit your runtime to the conformance registry at
   `labs.stellarminds.ai/conformance` for independent re-verification — lab
   re-run, counter-signature, or attested CI (a self-signed badge alone is not
   sufficient).

## Implementing ARP

ARP is runtime-agnostic — any agent stack can emit conformant receipts. Implement
the spec, pass `conformance/`, and ship a signed
[`sm-conformance`](https://github.com/Sharathvc23/sm-conformance) badge. The
receipt format depends on nothing but Ed25519, JCS, and the W3C `did:key` method.

## License

MIT — see [LICENSE](./LICENSE).
