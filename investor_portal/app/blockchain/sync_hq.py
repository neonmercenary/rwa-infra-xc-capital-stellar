#! app/scripts/sync_hq.py
from typing import List, Dict, Any
# ---------------------------------------------------------------------
# Here is where i realized i need Subnets for syncing as calling the state of the shared L1 kept throwing errors,
# This is just the reference implementation for syncing events from the blockchain when on a custom subnet.
# The workaround is in app/tasks.py where i use API to fetch the transaction state with the sync_blockchain_events function.
# This file contains functions to sync mint events and yield distributions from the blockchain.
# ---------------------------------------------------------------------

def sync_mints(contract, from_block: int) -> List[Dict[str, Any]]:
    """
    Sync mint events for backend indexing.
    """
    events = contract.Mint.query(
        from_block=from_block,
        to_block="latest",
    )

    return [
        {
            "tx": e.transaction_hash,
            "block": e.block_number,
            "investor": e.investor,
            "token_id": e.token_id,
            "slices": e.amount,
            "metadata_hash": e.metadata_hash,
        }
        for e in events
    ]


def sync_yields(contract, from_block: int) -> List[Dict[str, Any]]:
    """
    Sync yield distributions.
    """
    events = contract.YieldDistributed.query(
        from_block=from_block,
        to_block="latest",
    )

    return [
        {
            "tx": e.transaction_hash,
            "block": e.block_number,
            "token_id": e.token_id,
            "amount": e.amount,
        }
        for e in events
    ]
