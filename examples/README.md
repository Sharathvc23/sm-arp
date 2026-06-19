# Examples

Runnable demonstrations of `sm_arp`. Run from a checkout:

```bash
uv run python examples/full_set_demo.py
```

- **`full_set_demo.py`** — exercises the full ARP/VRP set end-to-end against the
  live package: action pricing, real Ed25519 signing, hash-chained receipts,
  counterparty corroboration, `nanda-rep` scoring with collusion-ring severance,
  the behavioral Merkle root, the `verifiable_receipts` AgentFacts facet, and
  authority-signed attestation. Every value is computed live, not hard-coded.
