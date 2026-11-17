# Changelog — sm-arp

## Unreleased — verifier MUSTs: freshness, reversal issuer, append-only logs

Public API changes are additive except the log behaviour below. No receipt bytes,
signature or chain link changes; the 25 existing vectors are byte-identical.

- **`verify_receipt(..., now=, max_skew_seconds=)`: `issued_at` freshness** (spec §3.3,
  §6.3 step 6). When `now` (an aware `datetime`) is given, `issued_at` must be within
  `max_skew_seconds` (default 300, inclusive) of it; stale and forward-dated
  receipts fail at the new `freshness` stage. Without `now`, nothing changes and old
  receipts still verify for audit. A naive `now`, a negative or non-int window, or a
  window without `now` raise `ValueError`. New `verify_freshness`,
  `DEFAULT_MAX_SKEW_SECONDS`.
- **`verify_receipt(..., originals=)`: reversal issuer** (spec §4.2). With an index of
  held receipts keyed by `receipt_id`, a reversal whose original is held must come
  from the original's issuer. The original's key must match its `receipt_id` and its
  signature must verify. A self-reversal or non-string reference fails. Failures use
  the new `reversal` stage. A reversal whose original is not held is not evaluated.
  New `verify_reversal`.
- **Receipt logs no longer rewrite or fork.** `ReceiptLog.append` used
  `INSERT OR REPLACE`, so re-appending a different receipt under an existing
  `(issuer_did, receipt_id)` silently replaced it, and nothing checked
  `previous_receipt_hash`. Now, in one write transaction:
  - every log (`ReceiptLog`, `AgencyLog`, `IssuerLog`) refuses a rewrite (same id,
    different signed content), refuses a re-append that would drop witness
    co-signatures, and refuses a fork (a second receipt by one issuer claiming the
    same predecessor). Re-appending an identical receipt is still a no-op. A copy
    with extra witnesses (detached evidence, §5.1) updates the stored copy.
  - `IssuerLog` is now a subclass of `ReceiptLog` that also requires each receipt to
    extend the issuer's current head: no gaps, no link into another issuer's chain,
    no branch off an older receipt, no second genesis once the issuer chains.
    `AgencyLog` stays `ReceiptLog`, because a principal's log holds partial,
    possibly out-of-order chains.
  - malformed key fields (non-string ids, a `previous_receipt_hash` that is present
    but not `sha256:<64 hex>`) are refused instead of raising `KeyError` or a SQLite
    binding error.
  - refusals raise the new `AppendRefused(ValueError)`, with `.reason` set to
    `malformed`, `rewrite`, `fork` or `discontinuity`.
  **Behaviour change:** code that relied on `append` overwriting a stored receipt,
  or on storing a forked chain, now gets `AppendRefused`.
- **Conformance harness** gains the same `now` / `max_skew_seconds` / `originals`
  inputs and the `freshness` / `reversal` stages. Vectors 26–29 added (25 → 29). The
  CLI's `vectors run` honours `verifier_now`, and `arp verify` checks the reversal
  rule against originals in the same file.
- **Spec text corrected** (spec changelog "Unreleased"): §10.3 no longer claims a
  redacted receipt keeps a verifiable signature, and §16 describes the Attested
  Action Envelope as sm-aae implements it.

## 0.4.0 — detached witness evidence, authenticated authority chain, strict structure (audit 2026-11)

Fixes every finding of the 2026-11 audit of sm-arp and its consumers (sm-oversight,
sm-dat, sm-parc). The minor bump is for the canonicalization change below; existing
receipts without witnesses are unaffected byte-for-byte (none of the 22 pre-existing
vectors was re-signed), and the public API is additive.

- **`evidence.witness_signatures` is detached from the issuer signature and the hash
  chain** (spec §5.1 / §6.1 / §6.4, spec changelog v0.1.1). `canonical_bytes(...)` now
  excludes `evidence.witness_signatures` for both `include_signature` settings, dropping
  an `evidence` object the removal leaves empty; `chain_link` therefore no longer moves
  when a witness lands. `vrp._corroboration_payload` is now literally
  `canonical_bytes(r, include_signature=False)`, so the issuer signature, the chain link
  and the VRP corroboration payload share one rule — the one sm-oversight's
  `_quorum_bytes` already used. Before: sm-oversight's `add_witness` and VRP's
  `cosign_receipt` both invalidated the issuer's signature of the receipt they
  co-signed. New public helper `detach_witnesses(receipt)`.
- **`is_corroborated` accepts `signer_did` as an alias for `witness_did`** (the key
  sm-oversight writes); `witness_did` governs when both are present and
  `cosign_receipt` keeps writing `witness_did`.
- **`verify_authority_chain` authenticates the grant.** It now verifies the grant
  receipt's Ed25519 signature, requires the index key to equal the grant's `receipt_id`,
  requires a present, non-empty `granted_to_did` equal to the action's `issuer_did`,
  requires `grant_expires_at` to be a present, aware RFC 3339 timestamp compared as an
  instant against the action's `issued_at` (absent/empty/unparseable expiry fails; it
  used to mean "never expires" and was compared as a string), and requires a non-empty
  `granted_scope` list. Malformed grant objects fail at the `authority_chain` stage
  instead of raising. `verify_direct_grant` is unchanged.
- **Strict mode rejects unknown top-level members** (spec §3 MUST; the schema already
  enforced it with `additionalProperties: false`). `KNOWN_TOP_LEVEL_MEMBERS` exported.
  Note: `issue_receipt(..., composition=...)` emits a member the spec does not define;
  such receipts were never schema-valid and now also fail strict library verification.
- **`verify_receipt(mode=...)` and the conformance harness reject unknown modes with
  `ValueError`** instead of silently behaving as tolerant; `arp verify --mode` exits 2.
  `VERIFIER_MODES` exported.
- **README** no longer claims `verify_receipt(r).ok` checks authority and hash chain by
  default; it documents what the default does and how to enable the rest.
- **Vectors 23–25** (`23-witnessed-receipt`, `24-witness-tampered`,
  `25-unknown-top-level-member`); corpus 22 → 25, suite digest changes accordingly.


## 0.3.4

Direct grants require the named principal to sign the grant receipt.

## 0.3.3

Add opt-in authenticated direct-grant verification with explicit time and DAT evaluation. Existing receipt bytes and chain hashes are preserved.

## 0.3.1 — readable receipts

- **`render(receipt) -> str`.** A one-line, human-readable rendering of any receipt —
  its date, the issuer's `human_summary`, and the outcome when it is not a plain
  completion. Domain-agnostic: ARP renders the summary the issuer wrote, and a domain
  layer can supply richer phrasing on top. Gives every consumer a consistent baseline.

## 0.3.0 — DAT bridge

- **DAT bridge (§4.5 / DAT SPEC §9.1).** An `authority_granted` receipt can now
  reference a Delegated Authority Token instead of inlining a flat scope:
  - `dat_digest(dat)` — canonical SHA-256 over the signed DAT envelope, the value
    a receipt commits to so the cheap on-network grant and the rich off-ledger DAT
    cannot be separated or swapped.
  - `dat_grant_payload(dat)` — builds the `authority_granted` `machine_payload`
    carrying both the DAT reference (`dat_grant_id` + `dat_digest`) and the thin
    fields (`granted_scope` / `grant_expires_at` / `granted_to_did`), so DAT-unaware
    verifiers still work.
  - `verify_authority_chain(..., *, dats=None, dat_verifier=None)` — opt-in hooks
    that verify the digest commitment, check `granted_scope` agrees with the DAT's
    categories, and delegate rich constraint evaluation to an injected
    `dat_verifier` (sm-arp never imports sm-dat). Passing neither preserves exact
    pre-bridge behaviour. Backward compatible.

## 0.2.3 — typed package, leaner wheel, enforced lint/types

- **Ships `py.typed`** — `sm_arp` is now a PEP 561 typed package, so downstream
  consumers (mypy/pyright) pick up its inline type hints with no stub workarounds.
- **Leaner wheel** — the dev-only test subpackage (`sm_arp.tests`) is no longer
  shipped in the published wheel; tests still run from source/editable in CI.
- **Enforced lint + types** — CI now runs ruff (`E,F,I,UP,B,SIM,C4,RUF`),
  `ruff format --check`, and mypy `--strict` over `sm_arp/`.
- Added `examples/full_set_demo.py` — a runnable end-to-end demonstration of the
  full ARP/VRP set (pricing, Ed25519 signing, hash-chained receipts, corroboration,
  nanda-rep scoring + collusion severance, behavioral Merkle root, the
  `verifiable_receipts` facet, and attestation).

## 0.2.2 — commitment_* category consistency

The `commitment_entered` / `commitment_fulfilled` / `commitment_breached` action
categories were present in the normative JSON schema (`schema/arp/0.1/action.schema.json`),
weighted in `DEFAULT_CATEGORY_WEIGHTS`, and listed in spec §4.3 — but were missing from
`KNOWN_CATEGORIES` in `sm_arp/receipts.py`, so the strict library verifier rejected a
commitment receipt that the scorer was built to reward. The four sources now agree.

- `receipts.py`: add the three `commitment_*` categories to `KNOWN_CATEGORIES` (19 → 22),
  so commitment receipts strict-verify.
- spec §4.3: clarify the categories are valid in v0.1; only the detailed per-category
  `machine_payload` schema (the companion commitment spec) is deferred to v0.2.
- tests: `test_category_enumerations_agree` (drift guard pinning schema enum ==
  `KNOWN_CATEGORIES` == `DEFAULT_CATEGORY_WEIGHTS`) and
  `test_commitment_receipt_verifies_and_scores`.

### Docs

- WHITEPAPER: add §8 "Verifiable Reputation: From Receipts to Standing", covering
  the `sm_arp.vrp` reputation profile (commitment, self-attested `nanda-rep/0.1`,
  counterparty-corroborated + collusion-resistant `nanda-rep/0.2`, attestation)
  that shipped in 0.2.0 but was undocumented in the whitepaper. Abstract and the
  composition table updated to reference it; "normative reputation profile" added
  to Future Work.

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
