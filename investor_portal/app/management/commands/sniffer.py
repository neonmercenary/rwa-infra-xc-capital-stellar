import os
from django.core.management.base import BaseCommand
from django.conf import settings
from eth_utils import to_checksum_address
from web3.middleware import ExtraDataToPOAMiddleware 
from ape import networks

class Command(BaseCommand):
    help = "Dumps raw log data to find the correct event signatures."

    def add_arguments(self, parser):
        parser.add_argument('--network', type=str, default=settings.DEFAULT_NETWORK)

    def handle(self, *args, **options):
        target_address = to_checksum_address("0xF159B5511b4d53B61bE67Cc40cF26E8F6f546BF3")
        network_choice = options['network']

        with networks.parse_network_choice(network_choice) as provider:
            provider.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            
            # These are the specific blocks where your CSV says transactions happened
            blocks = [49994015, 49999668, 50000032]
            
            self.stdout.write(f"Sniffing logs at address {target_address}...")

            for b in blocks:
                logs = provider.web3.eth.get_logs({
                    "address": target_address, 
                    "fromBlock": hex(b), 
                    "toBlock": hex(b)
                })
                
                if not logs:
                    self.stdout.write(f"No logs found in block {b}")
                    continue

                for i, log in enumerate(logs):
                    self.stdout.write(f"\n--- LOG {i} AT BLOCK {b} ---")
                    self.stdout.write(f"TX HASH: {log['transactionHash'].hex()}")
                    self.stdout.write(self.style.SUCCESS(f"TOPIC0 (SIGNATURE): {log['topics'][0].hex()}"))
                    
                    for idx, topic in enumerate(log['topics'][1:]):
                        self.stdout.write(f"TOPIC{idx+1} (Indexed Param): {topic.hex()}")
                    
                    self.stdout.write(f"DATA (Unindexed Params): {log['data'].hex()}")