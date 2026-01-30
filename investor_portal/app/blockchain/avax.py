import json
from ape import Contract
from ethpm_types import ContractType
from ape import accounts, networks
from ape.utils import ZERO_ADDRESS
from decimal import Decimal

# --- Configuration ---

# Minimal ABI for USDC so we don't need to call Etherscan/Snowtrace
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

def get_contract(address):
    # 1. Load the ABI we generated manually
    with open("rwa.abi", "r") as f:
        abi_list = json.loads(f.read())
    
    # 2. Create the Type (This avoids triggering the compiler)
    rwa_type = ContractType(abi=abi_list, contractName="RWALite")
    
    # 3. Use Contract() instead of project.RWALite.at()
    # This is the "Safe" way to interact with a deployed contract
    return Contract(address, contract_type=rwa_type)


def check_balance(contract_addr, account_addr, token_id):
    c = get_contract(contract_addr)
    return c.balanceOf(account_addr, token_id)
