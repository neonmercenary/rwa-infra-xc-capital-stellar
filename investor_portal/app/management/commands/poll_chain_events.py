from django.core.management.base import BaseCommand
from django.conf import settings
import os
import json
from pathlib import Path
from decimal import Decimal

from web3 import Web3

from app.models import Loan, InvestorPosition


class Command(BaseCommand):
    help = "Poll blockchain for RWA1155 events (DividendsDeposited) and reconcile balances"

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR) / "rwa"
        artifacts = base / "artifacts"
        abi_file = artifacts / "RWA1155.abi.json"
        addr_file = artifacts / "RWA1155.address"
        last_block_file = artifacts / "last_block.txt"

        if not abi_file.exists() or not addr_file.exists():
            self.stdout.write(self.style.ERROR("ABI or contract address not found in rwa/artifacts. Run deploy_rwa.py first."))
            return

        ABI = json.loads(abi_file.read_text())
        address = addr_file.read_text().strip()

        RPC = os.getenv("AVAX_RPC_URL", "https://avax-fuji.g.alchemy.com/v2/") + os.getenv("ALCHEMY_KEY", "")
        w3 = Web3(Web3.HTTPProvider(RPC))
        if not w3.is_connected():
            self.stdout.write(self.style.ERROR(f"Cannot connect to RPC {RPC}"))
            return

        contract = w3.eth.contract(address=address, abi=ABI)

        latest = w3.eth.block_number

        if last_block_file.exists():
            try:
                last_block = int(last_block_file.read_text().strip())
            except Exception:
                last_block = max(0, latest - 1000)
        else:
            last_block = max(0, latest - 1000)

        from_block = last_block + 1
        to_block = latest

        if from_block > to_block:
            self.stdout.write(self.style.NOTICE("No new blocks to scan."))
            return

        # We will fetch DividendsDeposited logs and process them
        event_abi = None
        for item in ABI:
            if item.get("type") == "event" and item.get("name") == "DividendsDeposited":
                event_abi = item
                break

        if event_abi is None:
            self.stdout.write(self.style.ERROR("DividendsDeposited event ABI not found."))
            return

        # Build topic for the event signature
        signature_text = "DividendsDeposited(address,uint256,uint256,uint256)"
        topic0 = Web3.keccak(text=signature_text).hex()

        self.stdout.write(self.style.NOTICE(f"Scanning blocks {from_block}..{to_block} for DividendsDeposited"))

        try:
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": address,
                "topics": [topic0],
            })
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching logs: {e}"))
            return

        for log in logs:
            try:
                evt = contract.events.DividendsDeposited().processLog(log)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to decode log: {e}"))
                continue

            depositor = evt['args']['depositor']
            tokenId = evt['args']['tokenId']
            amount = evt['args']['amount']

            self.stdout.write(self.style.SUCCESS(f"DividendsDeposited tokenId={tokenId} amount={amount} from {depositor}"))

            # Try to reconcile with local Loan by token_id
            try:
                loan = Loan.objects.get(token_id=int(tokenId))
            except Loan.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"No Loan found for token_id {tokenId}; skipping reconciliation."))
                continue

            positions = InvestorPosition.objects.filter(loan=loan)
            total_slices = Decimal(loan.total_slices or 100)

            # amount is in USDC smallest unit (assumed 6 decimals); convert to decimal dollars
            amount_decimal = Decimal(amount) / Decimal(10 ** 6)

            for pos in positions:
                slices = Decimal(pos.slices_owned)
                if total_slices == 0:
                    share = Decimal(0)
                else:
                    share = (slices / total_slices) * amount_decimal
                pos.balance_due = pos.balance_due + share
                pos.save()

            self.stdout.write(self.style.SUCCESS(f"Reconciled {len(list(positions))} positions for Loan {loan.loan_id}"))

        # Save last processed block
        with last_block_file.open("w") as f:
            f.write(str(to_block))

        self.stdout.write(self.style.SUCCESS("Polling complete."))
