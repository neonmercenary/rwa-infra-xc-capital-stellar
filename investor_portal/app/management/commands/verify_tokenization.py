# run: python manage.py verify_tokenization <tx_hash>
from django.core.management.base import BaseCommand
from ape import networks
from app.models import Loan

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('tx_hash', type=str)

    def handle(self, *args, **options):
        tx_hash = options['tx_hash']
        
        with networks.parse_network_choice("avalanche:fuji:node") as provider:
            # Direct lookup by hash - Fuji nodes rarely fail this
            receipt = provider.get_receipt(tx_hash)
            
            if receipt.status == 1: # Success
                for event in receipt.events:
                    if event.event_name == "TokenCreated":
                        # Match the on-chain ID to your local record
                        loan = Loan.objects.get(loan_id=f"OFFCHAIN-{event.id}")
                        loan.tokenized = True
                        loan.onchain_id = event.id
                        loan.save()
                        self.stdout.write(self.style.SUCCESS(f"Loan {loan.id} is now LIVE"))