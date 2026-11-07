# Proposed ARP maintenance release supporting oversight 0.2

Baseline 7b2f46b, package 0.3.2, 177 tests passed on Python 3.12. Target an additive 0.3.x maintenance release subject to compatibility testing. Oversight can prototype against 0.3.2 today.

## Verification boundaries

Document verify_signature, verify_receipt, verify_authority_chain, check_chain and the optional DAT verifier with concrete input trust and clock assumptions. verify_authority_chain performs grant relationship checks. A missing grant reference currently permits standing authority, omitted grantee/expiry have permissive semantics, and expiry is compared to receipt issuance time. Callers requiring per-action approval need explicit stricter conditions. verify_receipt with grants does not independently authenticate each supplied grant. Show the sequence for an independently verified signed action and grant. Document how callers must supply authenticated policy and a trusted execution clock.

Add an opt-in composed verification API for externally supplied action and direct grant. Require a nonempty explicit grant reference, matching grant ID, valid signatures and structures for both inputs, matching principal and grantee, exact allowed category and bounded, parseable validity timestamps. Reject wildcard or missing restrictions in this strict profile. Use parsed instants and define boundary and offset behavior. Separate receipt-time historical evaluation from caller-supplied trusted time for a live validity check. Report the checked scope explicitly. Leave review policy and execution permission to oversight. Avoid a redundant helper if the same strict contract can be cleanly exposed as an additive option.

If policy requires a DAT, resolve the referenced DAT, verify digest and scope agreement, and require a capable injected verifier for the relevant conditions, including authenticity and applicable constraints. Missing resolver, verifier, evidence or unknown critical constraints must fail the strict operation. Document how the existing optional bridge behaves. Keep sm-dat an optional integration.

## Signing and evidence compatibility

Freeze existing canonical_bytes, chain_link, receipt signatures, prior links and VRP counterparty co-signature semantics. Publish golden fixtures generated from 0.3.2, including existing witness_did evidence. Document why appending evidence to an already issuer-signed receipt may invalidate that receipt signature or change its chain hash. Demonstrate an immutable ARP receipt with an external oversight vote. Oversight owns vote signing and eligibility. Defer a generic detached-attestation primitive until a second concrete consumer agrees on semantics and signing vectors.

## Robustness and tests

Exercise public verification paths with wrong container types, missing mandatory fields, invalid base64, unsupported keys, invalid timestamps and canonicalization failures. Strict verification of untrusted bounded inputs must return stable failures. Document input limits and the distinction between parsing raw bytes and verifying an already parsed object. Preserve existing valid callers, including standing authority and legacy DAT integrations, under their existing APIs. If malformed or formerly tolerated inputs require behavioral changes, document them and assess release version separately.

Add tests for forged action and grant signatures, mismatched lookup key and embedded ID, swapped principal/grantee, wildcard or absent scope, historical vs live expiry, missing required DAT and invalid evaluator result. Run existing receipt, chain, CLI, conformance and VRP vectors unchanged, plus positive and negative cross-repository fixtures through oversight. Test the package installed from its built wheel on supported Python versions. Compare canonical bytes, receipt signatures and chain hashes to baseline fixtures. Run existing lint, typing and release gates.

## Rollout

First publish the verification-boundary documentation and fixtures. Implement and validate the additive strict path, publish a candidate wheel, and test it with oversight and representative existing consumers. Publish the maintenance release after the compatibility matrix passes. Update oversight's minimum dependency only if it uses the new API. Publish explicit legacy guidance and an example for consumers that currently equate authority-chain success with full authentication. Any incompatible wire proposal needs its own version and migration decision.
