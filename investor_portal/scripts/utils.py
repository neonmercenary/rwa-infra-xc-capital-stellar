"""Small utilities for interacting with IPFS via `aioipfs`.

Provides a simple `cat_file` coroutine and a convenience synchronous wrapper.
"""

import argparse
import asyncio
from typing import Optional

try:
    import aioipfs
except Exception:
    aioipfs = None  # defer import error until runtime use


async def cat_file(cid: str, addr: Optional[str] = None) -> bytes:
    """Fetch raw bytes for the given IPFS CID using aioipfs.

    Args:
        cid: the IPFS content identifier (CID) to fetch.
        addr: optional multiaddr of the IPFS node (not used by default client).

    Returns:
        Raw bytes of the content.
    """
    if aioipfs is None:
        raise RuntimeError("aioipfs is not installed; install with `pip install aioipfs`")

    client = aioipfs.AsyncIPFS()
    try:
        result = await client.cat(cid)
        return result
    finally:
        await client.close()


def cat_file_sync(cid: str, addr: Optional[str] = None) -> bytes:
    """Synchronous wrapper around `cat_file` using asyncio.run."""
    return asyncio.run(cat_file(cid, addr))


def _main() -> None:
    p = argparse.ArgumentParser(description="Fetch a file from IPFS via aioipfs")
    p.add_argument("cid", help="IPFS CID to fetch")
    args = p.parse_args()

    data = cat_file_sync(args.cid)
    # write to stdout (binary)
    import sys

    sys.stdout.buffer.write(data)


def tokenize_loan(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)

    if loan.tokenized:
        messages.info(request, "Loan already tokenized.")
        return redirect("app:loan_detail", loan_id=loan_id)

    # 1️⃣ Deploy contract (inside Django process)
    try:
        spv = get_spv()
        if not spv.private_key:
            raise RuntimeError("SPV wallet not configured")
        addr, abi = deploy_rwa_contract(spv.private_key)
    except Exception as e:
        messages.error(request, f"Deployment failed: {e}")
        return redirect("app:loan_detail", loan_id=loan_id)

    # 2️⃣ On-chain: create token
    try:
        receipt = create_token_onchain(
            contract_addr=addr,
            token_id=loan.id + 1000,
            initial_supply=int(loan.total_slices),
            price_usdc_units=int((loan.unit_price_usdc * Decimal(10**6))),
            uri = f"{settings.SITE_BASE_URL}/metadata/{loan.loan_id}.json",
        )
        if receipt is None:
            # nothing to do
            pass
        else:
            tx_hash = ""
            # if helper returned a receipt (web3.py receipt)
            if hasattr(receipt, "transactionHash") or isinstance(receipt, dict) and "transactionHash" in receipt:
                th = getattr(receipt, "transactionHash", None) or receipt.get("transactionHash")
                if isinstance(th, (bytes, bytearray)):
                    tx_hash = th.hex()
                else:
                    tx_hash = str(th)
                
            else:
                # helper returned tx_hash bytes/hex
                if isinstance(receipt, (bytes, bytearray)):
                    tx_hash = receipt.hex()
                else:
                    tx_hash = str(receipt)
            loan.tx_hash = tx_hash

    except Exception as e:
        messages.error(request, f"Token creation failed: {e}")
        return redirect("app:loan_detail", loan_id=loan_id)

    # 3️⃣ Persist
    _create_metadata_file(loan)
    loan.token_contract = addr
    loan.token_id = loan.id + 1000
    loan.tokenized = True
    loan.save()

    messages.success(request, "Tokenization completed.")
    return redirect("app:loan_detail", loan_id=loan_id)


if __name__ == "__main__":
    _main()