# app/scripts/public_functions.py
from ape import project, networks

class PublicRWA1155:
    def __init__(self, network_name: str = "avalanche", contract_address: str = None):
        self.network = networks.parse(network_name)
        self.contract = project.RWA1155.at(contract_address)

    def balance_of(self, address: str, token_id: int) -> int:
        return self.contract.balanceOf(address, token_id)

    def total_supply(self, token_id: int) -> int:
        return self.contract.totalSupply(token_id)

    def token_exists(self, token_id: int) -> bool:
        return self.contract.exists(token_id)

    def get_metadata_hash(self, token_id: int) -> str:
        return self.contract.metadataHash(token_id)
