# Changelog — sm-arp

## 0.2.1 — wheel ships only the library (no namespace pollution)

The published wheel now contains **only** the `sm_arp` library. Previously it also
shipped top-level `conformance` and `arp_cli` packages — a top-level `conformance`
collided with downstream consumers' own `conformance` modules, and because the wheel
didn't include the JSON schema files, the shadowing copy broke schema loading.

- `[tool.setuptools.packages.find] include = ["sm_arp*"]` (was `sm_arp*` + `conformance*`
  + `arp_cli*`).
- Removed the `arp` console-script entry point: the CLI (`arp_cli`) depends on the
  conformance harness and is now a repo/dev tool — run it from a checkout via
  `python -m arp_cli.cli`. The conformance harness, vectors, and schemas likewise stay
  in the repo (for `pytest conformance/`), just not in the wheel. `pip install -e .` for
  development still exposes all of it.

No library API change — `import sm_arp` / `sm_arp.vrp` is unchanged and now installs with
no extra top-level packages.

## 0.2.0 — VRP 0.3 counterparty-corroborated, collusion-resistant reputation

Brings `sm_arp.vrp` from VRP 0.1 to VRP 0.3 (`nanda-rep/0.2`): counterparty
corroboration, collusion severance, corroboration-gated scoring, and facts
attestation.

**§A — corroboration**
- `cosign_receipt(receipt, *, signing_key_bytes, witness_did=None)` — produce a
  counterparty co-signature (the `{witness_did, signature}` entry for
  `evidence.witness_signatures`).
- `is_corroborated(receipt)` — True iff a **distinct** counterparty co-signed the
  receipt and the signature verifies over the corroboration payload. Fully
  offline-recomputable from the receipt + the counterparty's `did:key`.

**§B — collusion severance.** Corroborations from collusion structure are voided:
build the corroboration graph, take its strongly-connected components, and sever any
component isolated from the honest anchor that is a dense ring (size ≥ 3, density
≥ 0.8) or a mutual-only pair.

**§C — scoring + ledger**
- `reputation_score_v2(receipts, *, is_valid, weights=…)` — category weights over
  GATED receipts (valid AND corroborated AND not collusion-severed).
- `corroboration_rate(receipts, *, is_valid)` — share of valid receipts that are
  corroborated and not severed.
- `build_ledger(..., method="nanda-rep/0.2")` now scores with §C and publishes
  `corroboration_rate`; `facet_from_ledger` carries it through; `verify_ledger`
  recomputes method-aware (rejects a tampered `corroboration_rate`). `method`
  defaults to `nanda-rep/0.1` — fully backward compatible.
- `did_key_from_pubkey(pubkey)` / `pubkey_from_did_key(did)` — the pubkey-bytes form
  of did:key derivation (agrees with `identity.did_from_sk`).
- `SCORING_METHOD_V2 = "nanda-rep/0.2"`.

A receipt is corroborated only when its counterparty (≠ issuer) signs the
**corroboration payload** — `JCS(receipt sans top-level "signature" and
`evidence.witness_signatures`)` — so a co-signer attests *what happened*, not the
issuer's signature. This is independent evidence the `nanda-rep/0.2` scoring method
requires before a receipt builds reputation.

No change to existing APIs; reuses `sm_arp.identity` for did:key. Still depends only
on `cryptography`, `base58`, `jcs`. Byte-exact output is pinned by embedded golden
vectors in `test_cosign.py` (§A) and `test_scoring.py` (§B/§C) — a corroboration or
score that diverged by a single byte would give an agent a different reputation
across implementations.

**Facts attestation (VRP 0.2 §A/§B)**
- `facts_digest(facts_record)`, `build_attestation(...)`, `verify_attestation(...)`,
  `AttestationVerification`, `LIFECYCLE_STATES`. An authority signs a facts record so
  a resolver establishes — without trusting any host — that this exact standing was
  vouched for, for this exact identity, over this exact ledger.

With this, `sm_arp.vrp` covers the full VRP 0.3 profile: corroboration, severance,
scoring, ledger, and attestation. Every layer is golden-pinned (`test_cosign.py`,
`test_scoring.py`, `test_attestation.py`).

## 0.1.x

ARP receipt envelope, did:key identity, IssuerLog, VRP 0.1 (`nanda-rep/0.1`)
scoring + behavioral Merkle root, and the conformance harness.
