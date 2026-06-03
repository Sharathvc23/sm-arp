"""arp — ARP v0.1 command-line tool.

Usage::

    arp verify <file>            # verify a receipt or trace (array)
    arp inspect <file>           # human-readable rendering
    arp walk-authority <file>    # walk action.granted_by_receipt_id back to root
    arp walk-chain <file>        # walk previous_receipt_hash back over time
    arp vectors list             # list the in-repo golden vectors
    arp vectors run <id>         # verify + explain one golden vector
    arp demo                     # the canonical 5-step tour for new audiences

Read-side only in this release. Issue/grant/revoke/keygen ship later.
"""

from arp_cli.cli import app, main

__all__ = ["app", "main"]
