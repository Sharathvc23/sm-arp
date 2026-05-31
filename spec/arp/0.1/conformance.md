# ARP Conformance Badge — v0.1

**Status:** Working Draft.
**Version identifier (wire):** `arp-conformance/0.1`.
**Last edited:** 2026-05-30.

> **Source of truth.** When a runtime disagrees with this specification, the runtime is wrong by definition. Behavior changes require a PR to this document, accompanied by updates to `schema/arp/0.1/conformance-envelope.json`, the badge vectors under `vectors/arp/0.1/conformance/`, and the reference verifier at `conformance/badge.py` + `conformance/verify_badge.py`.

---

## 1. Motivation

A runtime that claims to implement ARP needs a portable, self-describing artifact that records:

1. **Which version** of the conformance suite it passes.
2. **Which protocol versions** it implements.
3. **Who produced the run** (verifiable cryptographically).
4. **What the result was** (pass / fail counts, exit status).

This document specifies the **ARP Conformance Badge** — a JSON envelope a runtime ships at `.nanda/conformance.json` as the answer to those four questions in a single signed file.

The badge is the input to higher-level systems: registry admission, vendor onboarding gates, regulator audit, downstream-agent capability negotiation. None of those systems should accept a runtime's free-text claim of compliance; they consume the badge.

## 2. Conformance language

Normative requirements use RFC 2119 keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**. All other text is non-normative.

A "conformant ARP Conformance Badge producer" is one that emits envelopes whose serialized form passes the JSON Schema in `schema/arp/0.1/conformance-envelope.json`, signed per §7, with all fields populated per §5.

A "conformant ARP Conformance Badge verifier" is one that implements the algorithm in §9, refuses badges that fail any step, and (unless the operator explicitly opts in via `--allow-failures` or equivalent) refuses badges whose payload records `failed > 0` or `exit_status != 0`.

## 3. What the badge is and is not

> This section is normative. Implementations and downstream systems **MUST NOT** make stronger claims about a badge than this section permits.

A signed badge proves exactly two things:

1. **Authorship.** The holder of the Ed25519 private key whose public key is encoded in `signed_by` produced the signature. The signature binds the bytes of `payload` to that key.
2. **Claim.** The payload records that a suite run was performed and these were the counts, exit status, runtime name, and protocol versions.

A signed badge does **NOT** prove:

- That the suite was actually run (a key holder can hand-author a payload).
- That the counts are accurate (the payload contains numbers the signer chose).
- That the `suite_digest` reflects what was exercised — the digest is over the vector corpus present at run time, **not** over the subset of vectors a specific adapter exercised.
- That the signing key belongs to the runtime it claims to identify — DID-to-runtime binding is out of scope for this document and **MUST** be established by the consuming system (registry, vendor portal, regulator).

Systems consuming badges for admission, certification, audit, or trust decisions **MUST** establish additional evidence per §11.

## 4. Envelope

A badge is a JSON object with the following top-level shape:

```json
{
  "payload": { ... },
  "signed_by": "did:key:z...",
  "signed_at": "2026-05-30T12:00:00Z",
  "signature": "<base64>"
}
```

### 4.1 Required top-level members

| Field | Type | Notes |
|---|---|---|
| `payload` | object | See §5. The bytes signed are the canonical encoding (§6) of this object. |
| `signed_by` | string | `did:key:` of the signer. Public-key derivation per `spec/0.2/did-key.md`. |
| `signed_at` | string | RFC 3339 timestamp, UTC, with the `Z` suffix or `+00:00` offset. |
| `signature` | string | Standard-alphabet base64 of the 64-byte Ed25519 signature over `canonical_json(payload)`. |

### 4.2 Strictness

Unknown top-level members **MUST** be rejected by a strict verifier; a tolerant verifier **MAY** preserve them but **MUST NOT** include them in the canonical-encoding step (they are not signed and have no protocol meaning). No tolerant verifier exists in v0.1 — every conforming verifier is strict.

## 5. Payload

The `payload` object describes one run of the conformance suite.

### 5.1 Required payload members

| Field | Type | Notes |
|---|---|---|
| `schema_version` | integer | **MUST** equal `1`. Identifies the payload schema bound to this document. |
| `runtime` | string | Stable identifier of the runtime that produced the run. Examples: `"chapter"`, `"member-sdk"`, `"openclaw-skill"`, `"spec-reference"`. |
| `protocol_versions` | array of strings | Protocol versions (e.g. `"0.2"`, `"0.3"`) the run verified against. **MUST** be non-empty. |
| `suite_digest` | string | `sha256:<hex>` — the digest computed per §8. Pins the badge to a specific vector corpus. |
| `completed_at` | string | RFC 3339 timestamp marking when the run finished. |
| `exit_status` | integer | Process exit status of the run. `0` indicates the suite reported a passing run. |
| `passed` | integer | Number of tests that passed. **MUST** be ≥ 0. |
| `failed` | integer | Number of tests that failed. **MUST** be ≥ 0. |
| `skipped` | integer | Number of tests skipped. **MUST** be ≥ 0. |
| `xfailed` | integer | Number of tests marked expected-fail that did fail (the expected outcome). **MUST** be ≥ 0. |
| `xpassed` | integer | Number of tests marked expected-fail that unexpectedly passed. **MUST** be ≥ 0. |

### 5.2 Optional payload members

| Field | Type | When to include |
|---|---|---|
| `adapter` | string | The specific adapter the run used (e.g. `"spec-reference"`, `"member-sdk"`). Distinguishes "which signing helper was tested" from `runtime`. |
| `extensions` | object | Namespace-prefixed forward-compatible additions per ARP §12. Keys **MUST** be of the form `<namespace>.<field>`. Verifiers **MUST** preserve unknown extensions during re-serialization and **MUST NOT** fail on unrecognised extension keys. |

### 5.3 Field-level constraints

- A payload with `failed > 0` or `exit_status != 0` is a **valid** badge — it records a failing run — but **MUST NOT** be accepted by a verifier unless the verifier operator has explicitly opted in via `--allow-failures`. See §9.
- `passed + failed + skipped + xfailed + xpassed` **MAY** exceed the number of unique test cases (parametrized tests count once per parameter); verifiers **MUST NOT** assume this sum equals the test-case count.
- `runtime` and `adapter` strings **MUST** be ASCII and **SHOULD** match `[a-z0-9-]+`.

## 6. Canonical encoding

The signing procedure (§7) and the verification procedure (§9) require a deterministic byte string from the `payload` object. This document defines `canonical_json(payload)`:

1. Recursively sort all object members by key (UTF-8 byte order).
2. Serialize as JSON with:
   - No whitespace between tokens (separators `","` and `":"`).
   - UTF-8 encoding (`ensure_ascii = false`).
   - No trailing newline.
3. Return the UTF-8 bytes of the result.

**Normative encoding is RFC 8785 (JSON Canonicalization Scheme).** For payloads containing only ASCII strings, integers (signed 32-bit safe), booleans, `null`, and nested objects/arrays of the same, the simpler procedure above produces bytes **byte-identical** to JCS. Payloads that introduce non-ASCII strings, floating-point numbers, or `null` values in positions JCS treats specially **MUST** use proper JCS.

The reference implementation at `conformance/badge.py::canonical_json` uses the simpler procedure, valid for v0.1 payloads. A future payload schema that requires proper JCS will bump `schema_version`.

## 7. Signing

To produce a badge from a payload:

1. Construct the payload per §5. Every required member **MUST** be present.
2. Compute `C = canonical_json(payload)` per §6.
3. Sign `C` with Ed25519 using the runtime's private key. The signature is exactly 64 bytes.
4. Base64-encode the 64-byte signature using the standard alphabet with padding (`=`).
5. Derive `signed_by = did:key:z<base58btc(0xed01 ‖ pubkey32)>` per `spec/0.2/did-key.md`.
6. Set `signed_at` to the current UTC time in RFC 3339 form.
7. Emit the envelope `{ payload, signed_by, signed_at, signature }`.

The same private key **MAY** sign multiple badges over time. The `signed_at` field is not protected against replay by signature alone; consuming systems that care about freshness **MUST** establish a separate freshness signal (e.g. monotonic source, registry timestamp).

## 8. Suite digest

The `suite_digest` field pins the badge to a specific commit of the vector corpus. The reference algorithm at `conformance/badge.py::compute_suite_digest`:

1. List every `*.json` file under `vectors/` recursively.
2. Sort the list by POSIX relative path (UTF-8 byte order).
3. For each file in order, feed into a SHA-256 hasher:
   a. The relative path as UTF-8 bytes.
   b. A single `0x00` byte.
   c. The raw file bytes.
   d. A single `0x00` byte.
4. The digest is `"sha256:" + hex(hasher.digest())`.

> **What `suite_digest` does and does not pin.** It pins the **vector corpus present in the working tree at run time**. It does **not** pin the test code, the adapter implementation, or which subset of vectors a particular run exercised. A run with `--adapter=spec-reference` may exercise only signing vectors yet emit a digest that covers ARP, A2UI, and trust vectors. Verifiers **MUST NOT** infer "what was tested" from `suite_digest` alone; they **MAY** use it to refuse a badge that does not pin to a known suite version (§9.6).

A registry or downstream consumer **SHOULD** publish the `suite_digest` of the canonical suite at each tagged release and reject badges that do not match.

## 9. Verification algorithm

A conformant verifier, given a badge envelope `E`, **MUST**:

1. **Envelope shape.** Parse `E` as JSON. Reject if `payload`, `signed_by`, `signed_at`, or `signature` is missing or of the wrong type.
2. **DID resolution.** Parse `E.signed_by` per `spec/0.2/did-key.md` to recover the 32-byte Ed25519 public key. Reject if `signed_by` is not a `did:key:` of an Ed25519 multicodec key.
3. **Signature decode.** Base64-decode `E.signature` using the standard alphabet. Reject if not valid base64 or not exactly 64 bytes.
4. **Canonical recompute.** Compute `C = canonical_json(E.payload)` per §6.
5. **Verify.** Ed25519-verify the decoded signature over `C` using the resolved public key. Reject if verification fails.
6. **Suite-digest pin (optional).** If the verifier was configured with an expected `suite_digest`, reject if `E.payload.suite_digest` does not match exactly.

A conformant verifier, having completed steps 1–6, **MUST** additionally enforce the pass-gate:

7. **Pass-gate.** Unless the operator explicitly opts in via `--allow-failures` (or equivalent), reject if `E.payload.failed != 0` or `E.payload.exit_status != 0`.

Steps 1–6 constitute *signature verification*. Step 7 enforces *the badge's claim is "passed."* A verifier that omits step 7 produces "OK" for badges that record failures; that is a configuration the operator **MUST** explicitly request.

A verifier **SHOULD** additionally:

8. **Freshness.** Reject if `signed_at` is older than the operator's accept window. No default is specified by this document.
9. **DID-to-runtime binding.** Confirm `signed_by` matches the public key recorded for `runtime` in the operator's runtime registry. No default registry is specified by this document.

## 10. Verifier output

The reference verifier at `conformance/verify_badge.py` exits:

| Exit code | Meaning |
|---|---|
| `0` | All required checks (§9.1–§9.5), the suite-digest pin if configured (§9.6), and the pass-gate (§9.7) succeeded. |
| `1` | Envelope shape, signature, suite-digest pin, or pass-gate failed. |
| `2` | The badge file could not be read or parsed. |

Alternative verifiers **MAY** report differently but **MUST** distinguish at minimum between "verified and passing" and any other outcome.

## 11. Registry admission and external attestation

> This section establishes the boundary between what a self-signed badge proves and what consuming systems require beyond it. It is normative for any system that uses badges as input to admission, certification, audit, or trust decisions.

A self-signed badge — produced and signed by the same party — proves authorship and asserts a claim. It does **NOT** establish that the run actually happened or that the counts are accurate. Nothing in §7 prevents a key holder from hand-authoring a payload with chosen numbers and signing it.

A system that admits, certifies, or registers a runtime based on a badge **MUST** establish at least one of:

- **Independent re-run.** The system itself runs the conformance suite against the runtime's deployed surface (e.g. URL, container, package) and produces its own signed badge.
- **Counter-signature.** A trusted third party verifies the run and signs an envelope that wraps the runtime's badge. Both signatures are present and verifiable; the registry trusts the counter-signer.
- **Attested CI.** The runtime's badge is produced inside a build pipeline whose provenance attestation (SLSA, in-toto, Sigstore) the registry trusts. The badge's authenticity then derives from the CI's attestation chain, not the runtime's self-signature alone.

A registry that admits self-signed badges without one of the above is making a claim ("this runtime is conformant") that the badge does not substantiate. This document **prohibits** publishing such admissions under the ARP Conformance Mark.

## 12. Test vectors

Badge vectors live under `vectors/arp/0.1/conformance/`:

- `valid-signed-badge.json` — a complete envelope that verifies and passes the pass-gate.
- `tampered-payload.json` — same envelope, one payload field mutated; **MUST** fail at step §9.5.
- `tampered-signature.json` — one byte flipped in the signature; **MUST** fail at step §9.5.
- `wrong-signer.json` — `signed_by` replaced with a different did:key whose corresponding private key did not sign; **MUST** fail at step §9.5.
- `non-didkey-signer.json` — `signed_by` is a `did:web:` or other method; **MUST** fail at step §9.2.
- `missing-signature.json` — `signature` field absent; **MUST** fail at step §9.1.
- `failing-run.json` — well-formed signed envelope whose payload records `failed > 0`; **MUST** fail step §9.7 (pass-gate), **MUST** pass steps §9.1–§9.5 (signature is valid), **MUST** be accepted under `--allow-failures`.

Vectors are language-agnostic JSON. Any verifier in any language passes the same files.

## 13. Versioning

- `schema_version = 1` is bound to this document.
- Additive payload changes (new optional fields, new extension keys) **MAY** ship without bumping `schema_version`.
- Renamed, removed, or semantically changed fields **MUST** bump `schema_version` to `2`. A v1 verifier **MUST** reject a v2 payload at §5 validation (since `schema_version` is required and the verifier asserts `== 1`).
- The envelope shape (§4) is fixed for v0.1. A change to the envelope is a new major version of this document.

## 14. References

- ARP — `spec.md` (this directory). Defines the receipts whose runtime emits this badge.
- DID — `spec/0.2/did-key.md`. Public-key derivation for `signed_by`.
- Schema — `schema/arp/0.1/conformance-envelope.json` (JSON Schema for the envelope and payload).
- Reference implementation — `conformance/badge.py`, `conformance/verify_badge.py`, `conformance/conftest.py`.

[RFC 8785 JSON Canonicalization Scheme]: https://datatracker.ietf.org/doc/html/rfc8785
[Ed25519]: https://datatracker.ietf.org/doc/html/rfc8032
