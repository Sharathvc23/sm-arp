# NANDA Causal Delegation Trace — Working Prototype

A runnable, cryptographically verifiable 3-step **Causal Delegation Trace** for
Project NANDA, built on the Agency Receipt Protocol (ARP v0.1).

This directory is the missing "working prototype" layer for `sm-arp`: the spec
+ schemas + verifier already exist upstream; what was missing was a real
end-to-end example MIT researchers can feed into agent-interaction-trace
algorithms and audit byte-by-byte.

- **Spec (normative):** [`../spec/arp/0.1/spec.md`](../spec/arp/0.1/spec.md), in particular §4.6 (authority chain) and §6 (canonical signing).
- **Schemas:** [`../schema/arp/0.1/*.schema.json`](../schema/arp/0.1/) (JSON Schema 2020-12).
- **Verifier:** [`../conformance/arp/__init__.py`](../conformance/arp/__init__.py) — `verify_receipt(receipt, mode="strict")`.
- **CLI (developer tool):** [`../arp_cli/`](../arp_cli/) — `arp verify`, `arp walk-authority`, `arp render`, and the write-side (`arp keygen`/`issue`/`grant`/`revoke`). See [§Using the `arp` CLI](#using-the-arp-cli) below.

## TL;DR

Two ways to interact with this trace:

```sh
# (1) Regenerate + self-validate via the standalone script (no CLI install needed):
.venv/bin/python nanda/nanda_trace_demo.py

# (2) Or operate on the existing JSON via the arp CLI (pip install -e ".[cli]"):
arp verify          nanda/nanda_interaction_trace.json   # schema + Ed25519
arp walk-authority  nanda/nanda_interaction_trace.json   # §4.5 chain walk
arp render          nanda/nanda_interaction_trace.json   # human-facing diary view
```

The standalone script produces [`nanda_interaction_trace.json`](./nanda_interaction_trace.json) —
a JSON array of three Ed25519-signed receipts — and self-validates it against
the in-repo schemas and the §4.5 strict-mode authority-chain walk. Exits 0 on
success, nonzero on any violation. Deterministic: every run produces a
byte-identical file.

## The graph

```
   Receipt 1                       Receipt 2                       Receipt 3
   ─────────                       ─────────                       ─────────
   issuer:    Human                issuer:    Agent A              issuer:    Agent B
   principal: Human                principal: Human                principal: Human
   category:  authority_granted    category:  authority_granted    category:  data_shared
   scope:     [data_shared,        scope:     [data_shared]        counterparty: NANDA
               message_sent,                                                    Registry
               authority_granted]
                                   granted_by_receipt_id ───────► Receipt 1
                                   granted_to:  Agent B
                                                                   granted_by_receipt_id ─► Receipt 2
                                                                   authority_chain:
                                                                     [Human DID]
```

Three identities, three Ed25519 keypairs, three signed receipts. One directed
graph of delegated authority that any verifier with `did:key` resolution can
walk independently of the issuing runtime.

## The two edge types

ARP carries two backward-pointing references in receipts. Both are present in
this trace; they answer different questions.

| Edge | Field | Resolution | What it lets you verify |
|---|---|---|---|
| **Per-hop authority** | `action.granted_by_receipt_id` | UUID → the immediate authorizing receipt | "This action was authorized by **that specific grant**." Walk-by-walk, with all of §4.5's strict checks at every hop. |
| **Chain root** | `authority_chain` | Array of DIDs (or DAT envelope IDs) at the top level | "The root of this chain is **this** principal." Lets a consumer find the human at the root without walking every hop. |

Both edges are signed-over (they're inside the canonical JCS bytes Ed25519
covers), so neither can be tampered with after issuance.

## Reverse-traversal algorithm

The clean version, for MIT trace algorithms:

```python
def walk_authority_chain(receipt, receipts_by_id):
    """Return the chain [receipt, parent, grandparent, ..., root_grant].

    The last element is the genesis grant: its issuer_did is the human
    (or org) principal who rooted the chain. Raises if the chain references
    an unknown receipt.
    """
    chain = [receipt]
    current = receipt
    while gid := current["action"].get("granted_by_receipt_id"):
        if gid not in receipts_by_id:
            raise LookupError(f"chain references unknown receipt {gid}")
        current = receipts_by_id[gid]
        chain.append(current)
    return chain
```

Apply to the generated trace:

```python
import json
trace = json.load(open("nanda_interaction_trace.json"))
by_id = {r["receipt_id"]: r for r in trace}
chain = walk_authority_chain(trace[-1], by_id)   # start at Receipt 3
# chain[0]  → Receipt 3 (data_shared action)
# chain[1]  → Receipt 2 (sub-delegation)
# chain[2]  → Receipt 1 (genesis grant)
# chain[-1]["issuer_did"] == human principal DID
```

## Strict-mode authority-chain checks (spec §4.5)

For each edge `child → parent`, a strict verifier MUST confirm:

1. **Resolution.** The referenced `receipt_id` exists.
2. **Same principal.** `child.principal_did == parent.principal_did`. Only the
   principal can authorize their own agent chain. In this trace, both stay
   anchored to the human throughout — even Receipt 2, where Agent A is the
   issuer of the sub-grant.
3. **Parent is a grant.** `parent.action.category == "authority_granted"`.
4. **Not expired.** `parent.action.machine_payload.grant_expires_at >
   child.issued_at`.
5. **In scope.** `child.action.category` appears in
   `parent.action.machine_payload.granted_scope` (or `"*"` does).
6. **Not revoked.** No `authority_revoked` receipt by the principal references
   the parent before `child.issued_at`. (N/A in this trace — no revocations
   issued.)

`nanda_trace_demo.py` enforces checks 1–5 inline via `_walk_edge()` after
calling the cryptographic `verify_receipt()`. Together they cover schema +
Ed25519 + chain logic; if all three pass, the trace is mathematically sound
under ARP v0.1 strict mode.

A subtle but load-bearing detail in this trace: Receipt 1's `granted_scope`
includes `"authority_granted"` itself, because Receipt 2 has
`category=authority_granted` and points to Receipt 1 via
`granted_by_receipt_id`. Per check 5, the human is explicitly granting Agent A
the right to make sub-grants. Using `["*"]` would also satisfy the check but
is less auditable.

## Cryptographic guarantees, per receipt

- **Signing.** The body is JCS-canonicalized per RFC 8785, then signed
  Ed25519 with the issuer's private key. Signature is base64-encoded
  (88 chars, `==`-padded — exactly the `base64Ed25519Signature` schema
  pattern).
- **Identity.** `did:key` is multibase-z-base58btc over multicodec
  `0xed01 ‖ pubkey32` per W3C `did:key`. Any verifier can recover the
  32-byte Ed25519 public key from the DID alone — no registry lookup, no
  network round-trip.
- **Tamper-evidence.** The signature covers the full receipt body
  (including `action.granted_by_receipt_id`, `authority_chain`, and
  `machine_payload`), so neither the edges nor the scope can be rewritten
  after issuance without invalidating the signature.

## Verifying the trace locally

From the `sm-arp` repo root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .                          # pulls jcs, base58, cryptography, jsonschema
.venv/bin/python nanda/nanda_trace_demo.py          # regenerates the trace and self-validates
.venv/bin/pytest conformance/                       # runs the upstream conformance suite (25 tests)
```

Or independently, against the JSON output:

```sh
.venv/bin/python -c "
import json
from conformance.arp import verify_receipt
trace = json.load(open('nanda/nanda_interaction_trace.json'))
for r in trace:
    res = verify_receipt(r, mode='strict')
    print(r['receipt_id'], '→', res.stage, res.detail)
"
```

Expected output: three `accepted` lines.

For pure schema-only validation, point any JSON Schema 2020-12 validator at
`schema/arp/0.1/receipt.schema.json`. The schemas reference each other by
relative filename; you'll need to seed them into your validator's registry
(see `conformance/arp/__init__.py` `_load_registry()` for the exact pattern).

## Using the `arp` CLI

`pip install -e ".[cli]"` from the repo root exposes the `arp` entry point.
Everything below operates on the trace JSON in this directory.

```sh
# Verify all three receipts (schema + Ed25519 + hash chain). Auto-builds
# the priors map from the trace so any previous_receipt_hash links resolve.
arp verify nanda/nanda_interaction_trace.json
#   ✓ Receipt 1 [10000001-…] → accepted
#   ✓ Receipt 2 [20000002-…] → accepted
#   ✓ Receipt 3 [30000003-…] → accepted

# Walk the authority chain back to the root grant, enforcing every spec
# §4.5 strict-mode check at each hop (same principal, parent is a grant,
# unexpired, in-scope).
arp walk-authority nanda/nanda_interaction_trace.json
#   30000003-… (data_shared)
#   └─ 20000002-… (authority_granted)
#     └─ 10000001-… (authority_granted)
#   ✓ chain length = 3; root grant = 10000001-…

# Render as the principal's diary view (spec §10.1 Agency Log).
# Verifies before rendering — FORGED/MALFORMED receipts get a prominent
# warning instead of a misleading ✓. Authority links surfaced in prose.
arp render nanda/nanda_interaction_trace.json
#   Wed Jun 3, 2026 — 12:00 PM UTC  VERIFIED
#     ✓ Granted Agent A authority to share data and send messages on my behalf,
#       including the right to sub-delegate.
#     taken by you (the principal)
#
#   Wed Jun 3, 2026 — 12:15 PM UTC  VERIFIED
#     ✓ Sub-delegated data-sharing authority to Agent B under the Human Principal's grant.
#     taken by an agent on your behalf
#       ↳ under authority granted at Wed Jun 3, 2026 — 12:00 PM UTC:
#          "Granted Agent A authority to share data and send messages on my beh…"
#   ...
```

To inspect a single receipt with all fields (the developer view), use
`arp inspect <file>`. To pull the trace through the full 7-step demo
(adds purchase / GDPR / hash-chain / tamper-detection vectors around the
NANDA trace), use `arp demo`.

### Build a fresh delegation graph from the CLI

The CLI's write-side (`arp keygen` / `arp issue` / `arp grant` / `arp revoke`)
can reproduce this trace from scratch in shell — no Python needed:

```sh
HUMAN='your-32-byte-ascii-seed-for-h!!'
AGENT_A='your-32-byte-ascii-seed-for-a!!'
AGENT_B='your-32-byte-ascii-seed-for-b!!'

H=$(arp keygen --seed="$HUMAN"   | awk '/^did:/{print $2}')
A=$(arp keygen --seed="$AGENT_A" | awk '/^did:/{print $2}')
B=$(arp keygen --seed="$AGENT_B" | awk '/^did:/{print $2}')

arp grant --issuer-key="$HUMAN"   --principal="$H" --to="$A" \
          --scope="data_shared,message_sent,authority_granted" \
          --expires="2026-12-31T23:59:59Z" --out=r1.json

R1=$(jq -r .receipt_id r1.json)
arp grant --issuer-key="$AGENT_A" --principal="$H" --to="$B" \
          --scope="data_shared" --expires="2026-12-31T23:59:59Z" \
          --granted-by="$R1" --out=r2.json

R2=$(jq -r .receipt_id r2.json)
arp issue data_shared --issuer-key="$AGENT_B" --principal="$H" \
          --summary="Shared compliance summary with the NANDA Registry." \
          --counterparty-label="NANDA Registry" --granted-by="$R2" \
          --payload='{"fields_shared":["compliance_summary"]}' --out=r3.json

jq -s '.' r1.json r2.json r3.json > trace.json
arp verify trace.json && arp walk-authority trace.json
```

## Identities

Three deterministic 32-byte demo seeds (committed in the script):

| Role | Seed (ASCII) | DID |
|---|---|---|
| Human Principal | `nanda-demo-human-principal-32by!` | `did:key:z6MkoB8T2J2oPPCujP2qLSZn3jUM8b7dci5zmyWy4LEZoKUa` |
| Agent A | `nanda-demo-agent-a-seed-32-byte!` | `did:key:z6Mkgf6JomVa6Ha3rbrRsiHPDeRSNBsAEDSnM9sdMRomKKxh` |
| Agent B | `nanda-demo-agent-b-seed-32-byte!` | `did:key:z6MkgFT4qfJvW8MC8GT4itsVyFGqtd9o4CDyosns8AqqPymw` |

**Demo only.** These seeds are public — anyone with this file can sign as
these identities. Do not reuse them outside the demo. For a deployed NANDA
runtime, generate fresh seeds with `secrets.token_bytes(32)` and store the
private key in a key-management system.

## Where ARP fits in NANDA

NANDA's four pillars are DNS (discovery), CA (decentralized identity),
Orchestration (routing), and **Attestation** (verifiable evidence). ARP
contributes the per-action layer of Attestation — the complement to
`AgentFacts` (per-credential: what an agent *is*) and KYA (who vouches for
it). An ARP receipt records what an agent *did* on behalf of a human, under
which grant, with cryptographic provenance any verifier can check offline.

This trace demonstrates that the receipt format isn't just per-action — it's
**inter-action**: three signed receipts compose into a directed graph of
delegated authority that algorithms can traverse, audit, and reason about.

## Provenance

- **Spec:** ARP v0.1 Working Draft, May 2026. Normative document at
  `../spec/arp/0.1/spec.md`. Sections §3 (envelope), §4 (action object),
  §4.5–4.6 (authority chain), §6 (canonical signing), §12 (extensibility) are
  the load-bearing ones for this trace.
- **License:** MIT (see [`../LICENSE`](../LICENSE)).
- **Upstream:** [github.com/Sharathvc23/sm-arp](https://github.com/Sharathvc23/sm-arp).
- **Contribution context:** prepared for Project NANDA (MIT Media Lab) at
  an external request. ARP is runtime-agnostic and vendor-neutral by
  design; this directory contains the prototype layer, not the spec itself.
