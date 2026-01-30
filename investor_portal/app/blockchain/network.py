# app/blockchain/network.py
from enum import Enum

class Network(Enum):
    AVALANCHE = "avalanche"
    LISK = "lisk"
    # Add more networks here

class NetworkManager:
    def __init__(self):
        self.current_network = Network.AVALANCHE

    def switch_network(self, network: Network):
        self.current_network = network
        # Optional: setup RPC / provider URL dynamically
        print(f"Switched to network: {self.current_network.value.title()}")

    def get_rpc_url(self):
        # You can use .env or a config dict
        urls = {
            Network.AVALANCHE: "https://api.avax-test.network/ext/bc/C/rpc",
            Network.LISK: "https://testnet.lisk.io/api",
        }
        return urls[self.current_network]
