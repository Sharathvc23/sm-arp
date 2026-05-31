# Agency Receipt Protocol (ARP)

The portable, cryptographically signed receipt format AI agents emit when
they act on behalf of humans. Runtime-agnostic, vendor-neutral, MIT-licensed.

ARP sits above MCP (tool integration) and A2A (agent-to-agent transport)
— the **human ↔ agent accountability layer** those standards deliberately
do not address.

## Status

Working Draft v0.1, May 2026. Published-spec-first via
[labs.stellarminds.ai/arp](https://labs.stellarminds.ai/arp).

## Layout

- `spec/arp/0.1/spec.md` — the canonical normative document (RFC-style).
- `spec/arp/0.1/conformance.md` — Conformance Badge envelope spec.
- `spec/arp/0.1/governance.md` — stewardship and the path to public publication.
- `schema/arp/0.1/` — JSON Schemas (Draft 2020-12): receipt + badge.
- `vectors/arp/0.1/` — 22 receipt vectors.
- `vectors/arp/0.1/conformance/` — 7 conformance badge vectors.
- `conformance/arp/` — framework-agnostic Python conformance harness for receipts.
- `conformance/badge.py` + `verify_badge.py` — reference badge generator + CLI verifier.

## How to claim ARP compliance

1. Implement the spec in your runtime.
2. Run `pytest conformance/` against the bundled vectors. Every positive
   vector MUST pass; every negative vector MUST be rejected at the documented
   stage.
3. Generate a signed conformance badge per `spec/arp/0.1/conformance.md` and
   ship it at your runtime's `.nanda/conformance.json`.
4. Submit your runtime to the conformance registry at
   `labs.stellarminds.ai/conformance` for independent re-verification per
   conformance.md §11 (lab re-run, counter-signature, or attested CI).

## Reference implementations

The first reference implementations live in the NANDA Chapter Protocol
umbrella, which contributed this spec to the community:

- Chapter side: `chapter/arp.py`
- Member SDK side: `member-sdk/community_member/arp.py`
- Three currently-conformant runtimes ship signed badges at
  `*/.nanda/conformance.json` in that repository.

## License

MIT — see [LICENSE](./LICENSE).
