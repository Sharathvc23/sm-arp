# ARP — Agency Receipt Protocol — v0.1

**Status:** Working Draft.
**Version identifier (wire):** `arp/0.1`.
**Last edited:** 2026-05-21.

> **Source of truth.** When a runtime disagrees with this specification, the runtime is wrong by definition. Behavior changes require a PR to this document, accompanied by updates to `schema/arp/0.1/`, `vectors/arp/0.1/`, and every reference implementation. Conformance is verified mechanically via `conformance/arp/`.

---

## 1. Motivation

When an AI agent acts on behalf of a human (or organisation) — purchasing a service, sending a message, filing a record, agreeing to a contract — the human currently has no standardized, verifiable, human-readable record of what was done. Conversation logs are too low-level (thousands of tokens of LLM trace). Vendor receipts (Stripe, Uber, Amazon, calendar invites) are scoped to one merchant and tell the human nothing about *which* of their agents took the action or *under what authority*. There is no cryptographic link binding an action to the agent that took it, and no portable way for a third party — a regulator, an insurer, a downstream agent, the human themselves — to audit or dispute the action with evidence.

ARP defines a **portable Receipt envelope**: a cryptographically signed JSON record of one action taken by one agent on behalf of one human, in a shape any client can verify, archive, present, or dispute.

The protocol does not specify *which* actions an agent must record (that is a runtime policy decision, and likely a regulatory one in jurisdictions adopting the EU AI Act and analogous regimes). It specifies the *shape* of a receipt when one is emitted, so anyone can interpret it.

ARP is independent of the agent runtime (Claude, OpenAI, framework-based, custom), the platform hosting the agent, and the underlying tool-integration or transport protocols (MCP, A2A). It is the human-facing accountability layer above those protocols.

## 2. Conformance language

Normative requirements use RFC 2119 keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**. All other text is non-normative.

A "conformant ARP implementation" is one that:
1. Emits receipts whose serialized form passes the JSON Schemas in `schema/arp/0.1/`.
2. Computes signatures per §6 such that the receipts in `vectors/arp/0.1/` verify correctly.
3. Rejects every negative vector in `vectors/arp/0.1/` at the documented stage (schema, signature, hash chain, etc.).

## 3. Receipt envelope

A Receipt is a JSON object. Unknown members at the top level **MUST** be rejected by a strict verifier; an interoperability-tolerant verifier **MAY** accept and preserve them. (See §12 for the namespace-prefixed `extensions` carrier intended for forward-compatible additions.)

### 3.1 Required top-level members

| Field | Type | Notes |
|---|---|---|
| `version` | string | **MUST** equal `"arp/0.1"`. |
| `receipt_id` | string | UUIDv4 in canonical 8-4-4-4-12 form. **MUST** be unique across all receipts issued by the same `issuer_did`. |
| `issuer_did` | string | `did:key:` of the agent that issued the receipt. The signing key is derived from this DID. |
| `principal_did` | string | `did:key:` of the human (or human's identity-of-record) on whose behalf the action was taken. |
| `issued_at` | string | RFC 3339 timestamp, second precision, UTC, with the `Z` suffix. Example: `"2026-05-21T14:23:01Z"`. |
| `action` | object | See §4. |
| `signature` | string | base64-encoded (no padding stripped) Ed25519 signature over the canonical receipt (see §6). The signature **MUST** be exactly 64 bytes before base64 encoding. |

### 3.2 Optional top-level members

| Field | Type | Notes |
|---|---|---|
| `authority_chain` | array of strings | Identifiers (DIDs or DAT envelope IDs) of delegation grants that authorized this action. Empty or omitted means "relied on standing authority recorded at delegation time." See §7 and `dat-companion.md`. |
| `evidence` | object | See §5. |
| `previous_receipt_hash` | string | `sha256:<64-hex>` of the previous receipt by this issuer in lexicographic-by-`issued_at` order. When present, **MUST** form a valid hash chain (see §6.4). |
| `jurisdiction` | object | See §8. Records the legal/regulatory context applicable to the action — required when the action is regulated, recommended otherwise. |
| `accessibility` | object | See §9. Annotates the receipt for accessibility tooling (screen readers, machine translation, summary truncation). |
| `extensions` | object | Namespace-prefixed forward-compatible additions. Keys **MUST** be of the form `<namespace>.<field>` where `<namespace>` is a domain name owned by the publisher. Verifiers **MUST** preserve unknown extensions during re-serialization and **MUST NOT** fail on unrecognised extension keys. |

### 3.3 Field-level constraints

- `version`, `receipt_id`, `issuer_did`, `principal_did`, `issued_at`, and `signature` **MUST** be non-empty strings.
- `issued_at` **MUST** be within the verifier's accept window (default ±300 seconds from the verifier's current time, configurable per deployment). Outside this window the receipt **MUST** be rejected as stale.
- `issuer_did` and `principal_did` **MUST** be valid `did:key:` strings as defined in `spec/0.2/did-key.md`. Other DID methods are reserved for future versions.
- `receipt_id` collisions are receipt-issuer-scoped, not global; two different issuers **MAY** independently use the same UUID without error.

## 4. Action object

The `action` member describes what was done.

### 4.1 Required `action` members

| Field | Type | Notes |
|---|---|---|
| `category` | string | One of the values in §4.3. **MUST** be a known value; unknown values are rejected by strict verifiers. (Tolerant verifiers see §12.) |
| `human_summary` | string | One sentence in plain language, **MUST** be ≤ 280 Unicode code points (one Twitter-length), describing the action so that a human reading the receipt understands without context. Example: `"Booked a haircut at Supercuts Brookline for May 28 at 3pm, $35."` |
| `outcome` | string | One of: `completed`, `failed`, `partial`, `reversed`, `pending`. |

### 4.2 Recommended `action` members

| Field | Type | When to include |
|---|---|---|
| `counterparty_did` | string | When the counterparty has a DID. |
| `counterparty_label` | string | Human-readable name. Example: `"AMC Boston Common 19"`. |
| `amount` | object | `{ "currency": "<ISO 4217 3-letter code>", "cents": <integer> }`. Negative `cents` indicates outgoing from the principal's perspective. |
| `machine_payload` | object | Structured action-specific details. Schema is free-form by category; future minor versions of ARP **MAY** introduce per-category schemas. |
| `reversal_of_receipt_id` | string | When `category` involves undoing a prior action, the UUID of the receipt being reversed. The issuer **MUST** be the same as the original receipt's issuer; the verifier **MUST** check this. |

### 4.3 Action category enumeration

The following categories are defined in v0.1. Categories are case-sensitive lowercase snake_case identifiers.

| Category | Meaning | Notes |
|---|---|---|
| `purchase` | Spent money or committed to spending. | Typically paired with `amount.cents` negative. |
| `payment_sent` / `payment_received` | Money movement without an underlying purchase (transfers, refunds, payroll). | |
| `message_sent` / `message_received` | Communication with a counterparty. | Includes email, chat, push notifications, A2A messages. |
| `decision_made` | A choice with material consequence (declined an offer, picked option A over B, accepted terms). | `machine_payload.choice` SHOULD record the selected option and the alternatives. |
| `data_shared` | Disclosed information to a counterparty. | Sensitive — see §10 privacy. |
| `appointment_booked` / `appointment_cancelled` | Calendar commitment created or removed. | |
| `subscription_changed` | Started, paused, modified, or ended a recurring service. | `machine_payload.delta` SHOULD describe before/after. |
| `record_filed` | Filed something with a third party (tax authority, government, HOA, court). | High-stakes; jurisdiction §8 **SHOULD** be present. |
| `account_created` / `account_closed` | Identity binding to a service began or ended. | |
| `attestation_issued` / `attestation_received` | Trust-graph operation. | |
| `commitment_entered` / `commitment_fulfilled` / `commitment_breached` | A commitment was entered into, fulfilled, or breached. Valid v0.1 categories; the detailed per-category `machine_payload` schema (the companion commitment spec) is deferred to v0.2. | |
| `vote_cast` | Voted in any formal poll, governance, or DAO action. | |
| `authority_granted` | Principal granted an agent explicit authority for a scope of action categories with an expiration. See §4.6. | `machine_payload` MUST contain `granted_scope` (non-empty array), `granted_to_did`, `grant_expires_at`. |
| `authority_revoked` | Principal revoked a previously-granted authority. | `machine_payload` MUST contain `revokes_receipt_id` pointing to the original grant. |
| `other` | None of the above. `machine_payload.action_type_label` **MUST** be present. | |

Future versions of ARP **MAY** introduce new categories. Verifiers operating in tolerant mode (see §12) **MUST** present unknown categories as `category=other` with the unknown value preserved in `machine_payload.action_type_label`.

### 4.4 `human_summary` quality

`human_summary` is the principal's primary affordance for reading a receipt. It **MUST**:

- be a single sentence ending in a period, question mark, or exclamation point;
- be in the principal's preferred language (see §9.2);
- name the counterparty, the action, and where applicable the amount;
- avoid jargon (`POST`, `404`, `JWT`, `API`, internal IDs) unless the principal explicitly opted into technical summaries via runtime policy.

A receipt whose `human_summary` is empty, machine-generated boilerplate (`"action completed"`), or a re-statement of the JSON keys **MUST** be considered conformant by the schema but **SHOULD** be flagged for review by audit tooling. Issuers **SHOULD** track the rate of low-quality summaries as a quality metric.

### 4.5 `action.granted_by_receipt_id` — authority chain

Optional UUID field referencing a prior `authority_granted` receipt that authorizes this action. Verifiers in **strict mode** (see §12) **MUST**:

1. Resolve the referenced receipt by `(issuer_did, receipt_id)`.
2. Confirm the referenced receipt's `principal_did` equals this receipt's `principal_did` (only the principal can authorize their own agent).
3. Confirm the referenced receipt's `action.category == "authority_granted"`.
4. Confirm the referenced receipt's `action.machine_payload.grant_expires_at` is in the future relative to this receipt's `issued_at`.
5. Confirm this receipt's `action.category` appears in the referenced receipt's `action.machine_payload.granted_scope`, OR `"*"` appears in `granted_scope`.
6. Confirm no `authority_revoked` receipt has been issued by the same `principal_did` referencing the original grant before this receipt's `issued_at`.

If any check fails, the receipt **MUST** be flagged `authority_chain_invalid` and rejected in strict mode. Tolerant verifiers (see §12) **MAY** accept the receipt but **MUST** surface the failure to the audit consumer.

### 4.6 Authority chain — model and motivation

Agents acting on behalf of humans need a tamper-evident record of *what authority the agent was granted to take this action*. Without that, every action receipt is "the agent says it did X" with no link back to "the human consented to X being done."

The authority chain is a two-receipt pattern:

1. **Grant receipt**: The principal (or a delegate already authorized to grant) emits a receipt with `action.category == "authority_granted"`. The `machine_payload` contains:
   - `granted_scope`: array of action categories the grant covers (use `["*"]` for any category).
   - `granted_to_did`: the agent receiving the authority.
   - `grant_expires_at`: RFC 3339 timestamp; verifiers reject actions after this time.

2. **Action receipt**: The agent, when taking an authorized action, references the grant via `action.granted_by_receipt_id`. Strict verifiers check the linkage per §4.5.

3. **Revocation receipt** (optional): The principal can revoke a grant at any time by emitting a receipt with `action.category == "authority_revoked"` and `machine_payload.revokes_receipt_id` set to the grant's receipt ID. After revocation, any later action receipt referencing the revoked grant fails verification.

This pattern enables:

- **CCPA/CPRA consent records**: the grant receipt IS the consent record. Right-to-know returns the full chain.
- **DoD authority-to-operate (ATO)**: each agent action is provably authorized by a specific grant traceable to a human approver.
- **Sovereign agent boundaries**: the SDK's principal can grant narrow scope (e.g. `["intent_submitted", "message_sent"]`) without granting `["data_shared"]`. Out-of-scope actions fail verification.

v0.1 does NOT mandate authority chains — they remain optional for backward compatibility. v0.2 may make them required for specific action categories (likely `data_shared`, `payment_sent`, and `record_filed`).

## 5. Evidence object

`evidence` is optional, structured pointers to artifacts that substantiate the action. Receipts that include evidence are stronger under dispute; receipts without evidence still verify cryptographically but rely on the issuer's reputation alone.

| Field | Type | Notes |
|---|---|---|
| `screenshots` | array of `{ hash, mime, ref? }` | `hash` is `sha256:<hex>`; `mime` is the IANA media type; `ref` is an optional URL or content-addressable identifier from which the artifact can be retrieved. |
| `external_refs` | array of strings | URLs, transaction IDs, confirmation numbers from third-party systems. Free-form text; verifiers do not dereference. |
| `prompt_lineage_hash` | string | `sha256:<hex>` of the prompt chain that produced this action — tamper-evident lineage of what the agent was instructed to do. The full prompt is held privately by the issuer; only its hash is published. |
| `decision_trace_hash` | string | `sha256:<hex>` of the agent's internal reasoning trace, if recorded. Same privacy posture as `prompt_lineage_hash`. |
| `tool_invocations` | array of `{ tool_did, mcp_server_uri?, request_hash, response_hash, timestamp }` | When the action involved MCP tool invocations, summary of each. Hashes preserve audit-ability without leaking content. |
| `witness_signatures` | array of `{ witness_did, signature }` | Co-signatures from additional agents who attest to the action. Useful for high-stakes actions where the principal wants more than one signature. |

`evidence` and its fields are all optional. A verifier **MUST NOT** reject a receipt solely because `evidence` is missing or sparse.

## 6. Canonical signing

The Receipt **MUST** be signed with the issuer agent's Ed25519 private key. The signing procedure is:

### 6.1 Canonical-string construction

1. Take the full Receipt JSON object.
2. Remove the `signature` field if present.
3. Serialize per [RFC 8785 JSON Canonicalization Scheme] (JCS). This produces a deterministic byte string regardless of input ordering, whitespace, or encoding nuance.
4. The result is the canonical string `C`.

### 6.2 Signing

1. Sign `C` (as bytes) with Ed25519 using the issuer's private key. The signature is exactly 64 bytes.
2. Base64-encode the 64-byte signature using the standard base64 alphabet with padding (`=`).
3. Insert the resulting string as the `signature` field of the Receipt.

The issuer's public key is derived from `issuer_did` per `spec/0.2/did-key.md` (multibase `z` over `0xed01 ‖ pubkey32`).

### 6.3 Verification

A verifier **MUST**:

1. Parse the Receipt JSON.
2. Resolve `issuer_did` to a public key using the did:key method.
3. Compute the canonical string `C` per §6.1.
4. Decode the `signature` base64 to 64 bytes.
5. Verify the Ed25519 signature over `C` using the resolved public key. **MUST** reject if verification fails.
6. Check that `issued_at` is within the accept window (default ±300 s).
7. If `previous_receipt_hash` is present, fetch the prior receipt by its `receipt_id` (which **MUST** be discoverable in the issuer log) and verify that `sha256(<canonical bytes of prior receipt incl. its signature>)` equals the declared hash. **MUST** reject if the hash does not match.

A verifier **SHOULD** additionally:

8. Check that `principal_did` matches the principal binding expected for `issuer_did` (via a DAT grant or a platform ledger record), and reject if mismatched.
9. Check that `authority_chain` entries are valid, unrevoked, and cover the action category (when the DAT spec is in scope).

### 6.4 Hash chain

When an issuer chooses to maintain a hash chain across its receipts, each receipt's `previous_receipt_hash` **MUST** equal the SHA-256 hash of the previous receipt **including its `signature`**, computed over the JCS-canonicalized bytes of the full receipt.

The chain is per-issuer. Different agents issue independent chains. The "first" receipt in a chain (genesis) **MUST** omit `previous_receipt_hash`; later receipts **MUST** include it.

Hash chains are a strong tamper-evidence property but not all use cases require them. Issuers that do not maintain chains **MUST NOT** include `previous_receipt_hash` (presence-without-validity is a stronger failure than absence).

## 7. Authority chain

`authority_chain` is an optional array of identifiers pointing to delegation grants that authorized the action. Each identifier is either:

- a DID (e.g., `did:key:z6Mk...`) of a principal who explicitly granted authority, or
- a DAT envelope ID of the form `dat:<issuer-did>:<grant-uuid>` referring to a Delegated Authority Token envelope (see `dat-companion.md` for the v0.1-draft sketch).

In v0.1, `authority_chain` is descriptive: verifiers note it but do not yet evaluate the underlying grants. v0.2 will normalize the DAT spec and require verifiers to evaluate the chain.

An empty or absent `authority_chain` means the issuer relied on "standing authority" — the authority recorded at delegation time when the principal first bound their identity to the issuer. The audit trail for standing authority lives at the platform level, not inside individual receipts.

## 8. Jurisdiction

The `jurisdiction` object records the legal and regulatory context applicable to the action. It is **OPTIONAL** in general but **SHOULD** be present for actions in categories `purchase`, `payment_*`, `data_shared`, `record_filed`, `account_*`, `attestation_*`, `vote_cast`, and `commitment_*`.

### 8.1 Shape

| Field | Type | Notes |
|---|---|---|
| `principal_residence` | string | ISO 3166-1 alpha-2 country code, optionally followed by `-<ISO 3166-2 subdivision>` (e.g., `US-CA`, `IN-KA`, `DE-BY`). The principal's primary jurisdiction of residence at action time. |
| `action_locus` | string | Same format. The jurisdiction where the action was performed (e.g., the country where a payment was processed, the venue of an appointment). May equal `principal_residence`. |
| `data_residency` | array of strings | Same format. The jurisdictions where data related to the action is stored or transits. Important for GDPR / Schrems / PIPL. |
| `applicable_regimes` | array of strings | Identifiers of specific regulatory regimes the issuer asserts apply. Examples: `gdpr`, `ccpa`, `hipaa`, `pci-dss`, `eu-ai-act`, `coppa`, `lgpd`, `pipl`. Verifiers do not validate this list against the action; the field is for downstream compliance tooling. |
| `consent_evidence_hash` | string | Optional `sha256:<hex>` of the consent record the principal granted for this category of action. Pairs with §5 evidence. |

### 8.2 Why this matters

In a world of cross-border AI agents, an action's jurisdictional posture is rarely obvious from the parties alone. A US-resident principal using a German-hosted agent to file a Brazilian tax declaration touches three jurisdictions; future audits (regulatory, insurance, dispute) need that recorded at action time, not reconstructed years later. The `jurisdiction` block is the substrate that makes such audits tractable.

### 8.3 Conservative posture

When a runtime is uncertain about a value (e.g., the action_locus depends on which Stripe processor was used and the runtime cannot tell), the field **SHOULD** be omitted rather than guessed. False jurisdiction claims are worse than absent ones for downstream compliance use.

## 9. Accessibility

The `accessibility` object annotates the receipt for accessibility tooling. Receipts are read by humans, often by humans using screen readers, machine translation, summarization, or assistive language tools. The `accessibility` block makes those use cases first-class.

### 9.1 Shape

| Field | Type | Notes |
|---|---|---|
| `summary_language` | string | BCP 47 language tag of `human_summary` (e.g., `en`, `en-US`, `ja`, `es-MX`). **SHOULD** be present whenever the summary language can be determined. |
| `alt_summaries` | array of `{ lang, summary }` | Alternative-language renderings of `human_summary`. Each entry has the same length constraints as the primary summary. Used by the principal's diary application when their preferred language differs from the issuer's default. |
| `screen_reader_hints` | object | Hints for assistive technology rendering. See §9.3. |
| `complexity_level` | string | One of `simple`, `moderate`, `complex`. Hint to UI tooling for whether the principal should see additional context. `simple` is suitable for a passive notification; `complex` should be queued for review. |
| `requires_review` | boolean | When `true`, the issuer flags that the principal **SHOULD** explicitly review this receipt rather than auto-acknowledging. Use sparingly — for high-value purchases, irreversible actions, sensitive data shares, and similar. |

### 9.2 Language-of-record

If the principal's identity-of-record (via DAT or platform binding) declares a preferred language and the issuer's `summary_language` differs, the issuer **SHOULD** include an `alt_summaries` entry in the principal's language. The principal's diary application uses `alt_summaries` to render the receipt in the user's preferred language; if no matching `alt_summaries` entry exists, the primary `human_summary` is used.

### 9.3 Screen-reader hints

`screen_reader_hints` is an object that **MAY** contain:

| Field | Type | Notes |
|---|---|---|
| `aria_label` | string | An override label for screen-reader announcement, when the `human_summary` is awkward when read aloud (e.g., contains URLs or codes). |
| `pronunciation` | object | Mapping of tokens within the summary to phonetic guides. Example: `{ "AMC": "ay em see" }`. Useful for proper nouns and acronyms. |
| `priority` | string | One of `routine`, `notable`, `urgent`. Lets assistive tooling decide whether to announce immediately or batch. |

### 9.4 Requirement strength

Implementations **SHOULD** populate at least `summary_language` whenever it can be inferred reliably. `requires_review` **SHOULD** be set conservatively (only when the principal genuinely needs to look). The rest is optional and tooling-dependent.

## 10. Storage and visibility

ARP does not mandate where receipts are stored, but defines two roles:

### 10.1 Agency Log

The **Agency Log** is the principal's authoritative store of their own receipts. It **SHOULD** be under the principal's control — a local file, an encrypted backup, a sovereign cloud store the principal owns. Issuers **SHOULD** push every receipt to the principal's Agency Log promptly (target: within 60 seconds of action completion).

The Agency Log is the canonical reference for "what my agent did on my behalf." A principal whose Agency Log diverges from an issuer's Issuer Log has the basis for a dispute.

### 10.2 Issuer Log

The **Issuer Log** is the agent's audit-side store. It **SHOULD** be hash-chained (see §6.4) for tamper-evidence. Chapters or platforms **MAY** operate an Issuer Log on behalf of their member agents. The Issuer Log is the canonical reference under audit, regulatory inquiry, or insurance dispute.

Receipts **MUST** be retrievable by `receipt_id` from at least one of these stores. Best practice: both, with periodic reconciliation (the divergence between them is itself audit-grade evidence).

### 10.3 Visibility tiers

Receipts contain potentially sensitive information. The protocol defines three visibility tiers:

| Tier | Fields visible | Audience |
|---|---|---|
| Principal-visible (always) | every field, including `evidence`, `machine_payload`, `human_summary` | the principal whose `principal_did` matches |
| Counterparty-visible (default) | `receipt_id`, `issuer_did`, `issued_at`, `action.category`, `action.outcome`, `action.amount`, `signature` | the counterparty named in `action.counterparty_did` |
| Public (opt-in) | none by default | nobody, unless principal explicitly publishes |

The principal **MAY** publish receipts (e.g., for proof-of-work portfolios, public attestations, transparency reports). The runtime publishing tool **MUST** support a "redacted publish" mode that strips `human_summary`, `machine_payload`, `evidence`, and `accessibility.alt_summaries` while preserving the signature over the original canonical string. (This is achievable because JCS canonicalization is deterministic — the signature continues to verify against the original, redacted receipts include both the redacted body and the unmodified signature.)

## 11. Security considerations

### 11.1 Forgery

Receipts are signed by the issuer, not the principal. A compromised issuer key can forge receipts. Key rotation procedures (per `spec/0.2/protocol.md` §2) **MUST** apply. Principals **SHOULD** monitor for receipts from `issuer_did`s they did not authorize.

### 11.2 Replay

`receipt_id` uniqueness, `issued_at` window enforcement (default ±300 s), and (when present) the `previous_receipt_hash` chain together prevent replay as a duplicate event. Verifiers **MUST** maintain a bounded `(issuer_did, receipt_id)` set with TTL ≥ 600 s and reject duplicates.

### 11.3 Hash-chain tampering

If `previous_receipt_hash` is present, the chain is verifiable end-to-end. Out-of-order chains, broken links, or chains that diverge from a known checkpoint **MUST** be rejected as audit evidence. Issuers **SHOULD** publish periodic chain checkpoints (a signed root hash at known intervals) so verifiers can detect rewrites.

### 11.4 Counterparty repudiation

ARP does not require the counterparty to countersign. A counterparty who denies the action requires evidence beyond the receipt — typically the corroborating receipt from the counterparty's own agent (when applicable), screenshots, third-party confirmations from `evidence.external_refs`, or witness co-signatures from `evidence.witness_signatures`.

### 11.5 Principal repudiation

A principal **MAY** dispute their own `authority_chain` — claim the chain points to a grant they did not issue, or to a grant that was revoked. Resolution of such disputes belongs to the DAT spec and the runtime's dispute-resolution protocol, not ARP.

### 11.6 Privacy leaks via summary

`human_summary` is principal-visible by default but it is also the easiest field to leak by accident (e.g., screenshotted by the principal and shared). Issuers **SHOULD** avoid putting sensitive information (full account numbers, medical conditions, full addresses) in `human_summary` and use `machine_payload` for the structured detail.

### 11.7 Side-channel leakage via `evidence`

`prompt_lineage_hash` and `decision_trace_hash` are hashes, but the hashed content (the prompt, the trace) may be sensitive. Issuers **SHOULD** salt the hash inputs with a per-receipt nonce to prevent rainbow-table reconstruction of common prompts. The nonce **SHOULD** be stored alongside the hashed content in the Issuer Log so reconstruction is possible at audit time but not by an attacker.

### 11.8 Signature scheme

v0.1 mandates Ed25519. Future versions **MAY** introduce additional schemes via `signature_scheme` field (currently implicit). Verifiers that pre-date the new scheme **MUST** reject receipts they cannot verify (fail-closed); they **MUST NOT** silently treat unknown schemes as valid.

## 12. Extensibility and forward compatibility

### 12.1 The `extensions` member

Forward-compatible additions to a receipt go in the top-level `extensions` object. Keys **MUST** be namespace-prefixed in the form `<namespace>.<field>` where `<namespace>` is a domain name owned by the publisher (e.g., `acme.example.workflow_id`, `mit.edu.experiment_arm`).

Verifiers:

- **MUST** preserve unknown extensions during re-serialization.
- **MUST NOT** fail verification on unrecognised extension keys.
- **MUST** include the entire extensions object in the canonical signing string per §6.1 (it is part of the receipt body).

### 12.2 New action categories

Future versions of ARP **MAY** introduce new `category` values. Verifiers operating in "strict" mode reject unknown categories; verifiers in "tolerant" mode (default for archival and viewer tools) preserve the unknown category and present it as `category=other` with the original value in `machine_payload.action_type_label`.

Implementations **SHOULD** document which mode they operate in. Issuers **SHOULD NOT** emit unknown categories without an accompanying spec PR.

### 12.3 Version negotiation

A receipt's `version` field is its self-declaration. Verifiers **MUST** check the version and apply the appropriate validation rules. v0.1 verifiers **MAY** reject `arp/0.0` (no prior versions exist) but **MUST** be prepared to coexist with future minor versions (`arp/0.2`, `arp/0.3`) that add fields without breaking v0.1 receipts.

A major-version increment (`arp/1.0`) is reserved for breaking changes — removed required fields, changed signing scheme, changed canonicalization.

## 13. Worked example

A purchase action by a member agent on behalf of a human principal:

```json
{
  "version": "arp/0.1",
  "receipt_id": "8c4a7f9a-3d1c-4b8e-9f2a-1b3c4d5e6f7a",
  "issuer_did": "did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw",
  "principal_did": "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp",
  "issued_at": "2026-05-21T14:23:01Z",
  "action": {
    "category": "purchase",
    "human_summary": "Booked 2 tickets to The Substance at AMC Boston Common 19, Friday May 23 at 8pm, $34.50.",
    "outcome": "completed",
    "counterparty_did": "did:key:z6MkfTBd5dPYbWZRZkVz4ZBz1ymuepAQ4HEHYSF1H8quG5GL",
    "counterparty_label": "AMC Boston Common 19",
    "amount": { "currency": "USD", "cents": -3450 },
    "machine_payload": {
      "movie": "The Substance",
      "showtime": "2026-05-23T20:00:00-04:00",
      "seats": ["F12", "F13"],
      "confirmation": "AMC-7HQ29X"
    }
  },
  "authority_chain": ["dat:did:key:z6Mki...:movies-budget-grant-q2"],
  "evidence": {
    "external_refs": ["AMC-7HQ29X"],
    "prompt_lineage_hash": "sha256:9c1b2a3d4e5f6789a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3"
  },
  "jurisdiction": {
    "principal_residence": "US-MA",
    "action_locus": "US-MA",
    "applicable_regimes": ["ccpa"]
  },
  "accessibility": {
    "summary_language": "en-US",
    "complexity_level": "simple",
    "requires_review": false
  },
  "signature": "rWZ6QyTtX/Hi+x3...base64-encoded-Ed25519-signature..."
}
```

## 14. Test vectors

20+ vectors at `vectors/arp/0.1/` exercise:

- core categories (`purchase`, `message_sent`, `decision_made`, `data_shared`, `record_filed`, `attestation_issued`, `vote_cast`)
- positive: signature verifies; schema passes; hash chain links
- negative: forged signature, tampered body, wrong hash chain, oversized `human_summary`, invalid `principal_did`, missing required field, mismatched `reversal_of_receipt_id` issuer
- forward-compat: unknown extension key (tolerant verifier accepts), unknown category (strict rejects, tolerant accepts as `other`)
- accessibility: receipts with `alt_summaries` for multiple languages, `requires_review=true`
- jurisdiction: GDPR-tagged data_shared, multi-jurisdiction data_residency

A conformance harness at `conformance/arp/test_arp_v01.py` executes every vector and asserts the documented expected outcome.

## 15. Reference conformance harness

A framework-agnostic conformance harness lives in this repository at `conformance/arp/test_arp_v01.py`. It executes every vector and asserts the documented expected outcome. Any runtime implementing ARP **MUST** pass it.

The suite is intentionally framework-agnostic — it loads vectors and verifies them against the JSON Schemas and Ed25519 signatures, exercising no runtime-specific code paths. A receipt implementation in any language passes the same vectors.

## 16. Relationship to the Attested Action Envelope (AAE)

ARP and the Attested Action Envelope (AAE) are **complementary** per-action evidence primitives, not competitors. They address different audiences and carry different properties:

- An **ARP receipt** is the *human-facing* record: a one-sentence `human_summary`, an `authority_chain` binding the action to a delegated grant, held by the represented human, a regulator, or an insurer. Its tamper-evidence is the per-issuer forward hash chain (§6.4).
- An **AAE envelope** is the *substrate* evidence record: the `action` / `decision` / `belief` / `checkpoint` kinds, rendered by operator surfaces, with `checkpoint` envelopes anchoring **bidirectional** (forward + reverse merkle-inclusion) audit over the envelopes in scope.

The two compose through a defined seam:

1. An ARP receipt's `evidence` **MAY** reference the AAE envelope(s) that substantiate the action — by the envelope's content hash — so a verifier can cross-walk from the human's receipt to the substrate evidence.
2. An AAE `checkpoint` **MAY** include ARP receipts among the records it commits to, so the bidirectional audit AAE provides extends to ARP receipts without ARP defining its own merkle layer.

ARP therefore **MUST NOT** define a bidirectional (checkpoint/merkle) audit mechanism of its own — when reverse-audit anchoring is required, an implementation relies on AAE via the seam above. Conversely, AAE carries no `human_summary` or `authority_chain`; those remain ARP's. An implementation **MAY** emit both for a single action — an ARP receipt for the human, an AAE envelope for the substrate — linked by the evidence reference. Neither primitive is redundant: each owns what the other deliberately omits.

## 17. Governance and stewardship

See [`governance.md`](./governance.md) for the change process, the contributor agreement, and the planned path to public publication via labs.stellarminds.ai/arp.

## 18. Open questions for v0.1 → v0.2

- **DAT formalization.** v0.1 references `authority_chain` descriptively; v0.2 will make DAT normative with full evaluation rules.
- **Counterparty co-signing.** Mandatory for some action categories (commitment_*) or optional? Likely category-dependent.
- **Receipt revocation.** A receipt cannot be "deleted" (signatures are permanent), but a revocation receipt that supersedes a prior receipt with `outcome=reversed` is the convention. Worth a stronger explicit primitive in v0.2.
- **Multi-principal actions.** What if an agent acts on behalf of two humans (couple booking joint flight)? v0.1 mandates a single `principal_did`; v0.2 may extend.
- **MCP tool-invocation correlation.** `evidence.tool_invocations` is sketched; v0.2 should define a canonical join key between an MCP server's audit log and an ARP receipt.
- **EU AI Act mapping.** The Act's Article 13 transparency provisions land 2027; v0.2 **SHOULD** include a normative mapping appendix showing how a complete ARP receipt satisfies each Article 13 sub-clause.

---

## Appendix A. Glossary

| Term | Definition |
|---|---|
| **Receipt** | The signed envelope defined in §3. |
| **Issuer** | The agent that signs and emits the receipt; identified by `issuer_did`. |
| **Principal** | The human (or organisation's identity-of-record) on whose behalf the action was taken; identified by `principal_did`. |
| **Counterparty** | The other party in the action (a merchant, a person, another agent). |
| **Agency Log** | The principal-controlled store of their own receipts. |
| **Issuer Log** | The agent-controlled, typically hash-chained, audit store. |
| **DAT** | Delegated Authority Token — companion spec defining the `authority_chain` semantics. |
| **JCS** | JSON Canonicalization Scheme, RFC 8785. |

## Appendix B. References

- RFC 2119 / RFC 8174 — Key words for use in RFCs.
- RFC 8785 — JSON Canonicalization Scheme.
- RFC 3339 — Date and Time on the Internet: Timestamps.
- W3C did:key Method — the W3C did:key specification.
- BCP 47 — Tags for Identifying Languages.
- ISO 3166-1 / ISO 3166-2 — Country and subdivision codes.
- ISO 4217 — Currency codes.
- IANA Media Types — for `evidence.screenshots.mime`.
- EU AI Act, Article 13 — transparency obligations.
- GDPR Articles 5, 6, 30 — data residency and processing records.
- HIPAA §164.312(b) — audit controls.

[RFC 8785 JSON Canonicalization Scheme]: https://datatracker.ietf.org/doc/html/rfc8785
