
import json
import os
from ethpm_types import ContractType
from ape import networks, Contract, accounts, project
from dotenv import set_key, load_dotenv, find_dotenv
from enum import Enum
from django.conf import settings

# 1. Load the .env file
ENV_PATH = find_dotenv(filename=".env")
if load_dotenv(ENV_PATH):
    print(f"✅ Loaded .env from {ENV_PATH}")




class NetworkConfig(Enum):
    AVALANCHE = "avalanche:fuji:alchemy"
    LISK = "lisk:sepolia:node"
    PLUME = "plume:testnet:node"
    # Add others as needed
    
    @classmethod
    def get_connection(cls, network_name: str):
        """Helper to get string by name (e.g., 'avalanche')"""
        try:
            return cls[network_name.upper()].value
        except KeyError:
            return cls.AVALANCHE.value # Default
        

# --- DEPLOY OR LOAD MASTER CONTRACT ---    


def get_or_deploy_master(admin_account):
    if not networks.active_provider:
        print("❌ Error: No active network connection found.")
        return None

    current_network = networks.active_provider.network.name
    env_key = f"MASTER_RWA_ADDRESS_{current_network.upper()}"
    print(f"🔑 Looking for {env_key} in .env...")
    address = os.getenv(env_key)

    # --- PART 1: LOAD ARTIFACTS MANUALLY ---
    # We do this up front so we have the 'blueprint' for either .at() or .deploy()
    with open("rwa.abi", "r") as f:
        abi_list = json.loads(f.read())
        
    with open("rwa.bin", "r") as f:
        bytecode = f.read().strip()
        if not bytecode.startswith("0x"):
            bytecode = f"0x{bytecode}"

    rwa_type = ContractType(
        abi=abi_list, 
        deploymentBytecode={"bytecode": bytecode}, 
        contractName="RWALite"
    )

    # --- PART 2: ATTACH OR DEPLOY ---
    if address:
        print(f"♻️ Found existing Master in .env: {address}")
        # Bypass 'project.RWALite.at' by using 'Contract' with our manual type
        return Contract(address, contract_type=rwa_type)

    print(f"🚀 Deploying fresh Master Contract to {current_network}...")
    
    # Get USDC address (replace with your config logic)
    payment_token = os.getenv("FUJI_USDC_ADDRESS") 
    
    # Deploy using the manual type object
    new_master = admin_account.deploy(
        rwa_type, 
        f"RWA Notes {current_network.title()}", 
        "RWA", 
        payment_token
    )
    
    # Save results
    set_key(".env", env_key, new_master.address)
    os.environ[env_key] = new_master.address
    
    return new_master


# --- REPLACING YOUR MULTICALL LOGIC ---
from ape_ethereum import multicall   # ships with ape

def get_multicall_yields(positions):
    """
    positions: list-like with
        .loan.token_contract  -> 0x…  (str)
        .loan.token_id        -> int
        .investor.wallet_address -> 0x… (str)
    returns: list[int]  (withdrawable dividends)
    """
    if not positions:
        return []

    # build the bundle
    bundle = multicall.Call()
    for p in positions:
        contract = Contract(p.loan.token_contract)  # auto-load ABI if verified
        bundle.add(contract.withdrawableDividendOf,
                   p.loan.token_id,
                   p.investor.wallet_address)

    # single eth_call
    return list(bundle())