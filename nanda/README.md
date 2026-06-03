# NANDA Causal Delegation Trace — Working Prototype

A self-contained, cryptographically verifiable 3-step **Causal Delegation Trace**
for Project NANDA, built on the Agency Receipt Protocol (ARP v0.1).

This directory is a **standalone reproducer**. It vendors the ARP v0.1
verifier and JSON Schemas inline so the entire prototype runs without any
`pip install sm-arp` step — only the five small pip libraries listed in
[`requirements.txt`](./requirements.txt). Clone this folder, install, run.

- **Spec (normative, upstream):** [github.com/Sharathvc23/sm-arp/blob/main/spec/arp/0.1/spec.md](https://github.com/Sharathvc23/sm-arp/blob/main/spec/arp/0.1/spec.md) — in particular §4.6 (authority chain) and §6 (canonical signing).
- **Schemas, vendored:** [`./_arp_v01/schemas/*.schema.json`](./_arp_v01/schemas/) (JSON Schema 2020-12).
- **Verifier, vendored:** [`./_arp_v01/__init__.py`](./_arp_v01/__init__.py) — `verify_receipt(receipt, mode="strict")`. Snapshot of sm-arp v0.1.0.

## Quickstart (45 seconds)

```sh
pip install -r requirements.txt
python nanda_trace_demo.py
```

That produces [`nanda_interaction_trace.json`](./nanda_interaction_trace.json) —
a JSON array of three Ed25519-signed ARP receipts — and self-validates it
against the vendored schemas, vendored Ed25519 verifier, and the §4.5
strict-mode authority-chain walk. Exits 0 on success, nonzero on any
violation. Deterministic: every run produces a byte-identical file.

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

## Files in this directory

```
nanda/
├── README.md                          this file
├── requirements.txt                   5 pip-installable deps; no sm-arp
├── nanda_trace_demo.py                generator + self-validator
├── nanda_interaction_trace.json       committed output (byte-identical per run)
└── _arp_v01/                          VENDORED — sm-arp v0.1.0 snapshot
    ├── __init__.py                    verify_receipt + compute_chain_link
    └── schemas/
        ├── receipt.schema.json
        ├── action.schema.json
        ├── common.schema.json
        ├── evidence.schema.json
        ├── jurisdiction.schema.json
        └── accessibility.schema.json
```

The vendored `_arp_v01/` is a *snapshot* of the upstream verifier; for the
canonical (potentially evolving) implementation, see
[github.com/Sharathvc23/sm-arp/tree/main/conformance/arp](https://github.com/Sharathvc23/sm-arp/tree/main/conformance/arp).

## Verifying with an independent JSON Schema validator

The receipts are plain JSON-Schema-2020-12 documents. Any conformant
validator works — you don't need Python or the vendored verifier. Point
your validator at `_arp_v01/schemas/receipt.schema.json` and seed the
sibling schemas into its registry by relative filename.

## Identities (DEMO ONLY)

Three deterministic 32-byte seeds, committed in the script so the trace
is reproducible:

| Role | Seed (ASCII) | DID |
|---|---|---|
| Human Principal | `nanda-demo-human-principal-32by!` | `did:key:z6MkoB8T2J2oPPCujP2qLSZn3jUM8b7dci5zmyWy4LEZoKUa` |
| Agent A | `nanda-demo-agent-a-seed-32-byte!` | `did:key:z6Mkgf6JomVa6Ha3rbrRsiHPDeRSNBsAEDSnM9sdMRomKKxh` |
| Agent B | `nanda-demo-agent-b-seed-32-byte!` | `did:key:z6MkgFT4qfJvW8MC8GT4itsVyFGqtd9o4CDyosns8AqqPymw` |

**Do not reuse these seeds outside the demo.** They are public; anyone with
this file can sign as these identities. For a deployed NANDA runtime,
generate fresh seeds with `secrets.token_bytes(32)` and store the private
key in a key-management system.

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

## Going deeper — the parent project

This directory is the **prototype**. The full specification, conformance
vectors (22 of them), additional schemas, and a developer-facing CLI
(`arp verify`, `arp render`, `arp walk-authority`, `arp keygen`, `arp issue`,
`arp grant`, `arp revoke`, `arp demo`) live in the parent project:

  **[github.com/Sharathvc23/sm-arp](https://github.com/Sharathvc23/sm-arp)**

```sh
# Optional: install the parent project to get the `arp` CLI
git clone https://github.com/Sharathvc23/sm-arp.git
cd sm-arp && pip install -e ".[cli]"

# Then verify or render this trace via the CLI:
arp verify          nanda/nanda_interaction_trace.json
arp walk-authority  nanda/nanda_interaction_trace.json
arp render          nanda/nanda_interaction_trace.json     # human-facing diary view
```

## Provenance

- **Spec:** ARP v0.1 Working Draft, May 2026. Normative document at
  [`spec/arp/0.1/spec.md`](https://github.com/Sharathvc23/sm-arp/blob/main/spec/arp/0.1/spec.md).
  Sections §3 (envelope), §4 (action object), §4.5–4.6 (authority chain),
  §6 (canonical signing), §12 (extensibility) are the load-bearing ones
  for this trace.
- **License:** MIT.
- **Upstream:** [github.com/Sharathvc23/sm-arp](https://github.com/Sharathvc23/sm-arp).

