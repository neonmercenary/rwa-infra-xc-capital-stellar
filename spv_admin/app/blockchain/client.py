import json
import os
import random
import subprocess
from enum import Enum
from pathlib import Path
from django.conf import settings
from ethpm_types import ContractType
from ape import networks, Contract, accounts, project
from dotenv import set_key, load_dotenv, find_dotenv


# 1. Load the .env file
ENV_PATH = find_dotenv(filename=".env")
if load_dotenv(ENV_PATH):
    print(f"✅ Loaded .env from {ENV_PATH}")


class NetworkConfig(Enum):
    AVALANCHE = "avalanche:fuji:alchemy"
    LISK = "lisk:sepolia:node"
    PLUME = "plume:testnet:node"
    STELLAR = "stellar:testnet:node" #Demonstration
    # Add others as needed
    
    @classmethod
    def get_connection(cls, network_name: str):
        """Helper to get string by name (e.g., 'avalanche')"""
        try:
            return cls[network_name.upper()].value
        except KeyError:
            return cls.AVALANCHE.value # Default
        

def get_unlocked_admin():
    admin = accounts.load("spv_admin")
    # Pull the passphrase from your environment variable
    passphrase = os.getenv("SPV_ADMIN_PASSPHRASE", "heathens")
    print(f"🔐 Using admin account: {admin.address}")
    
    # This 'unlocks' the account for the rest of the script's life
    admin.set_autosign(True, passphrase=passphrase)
    return admin



load_dotenv()

class RWAFactory:
    def __init__(self, admin_account):
        self.admin = admin_account
        self.network_name = None
        
        # Anchor everything to Django's BASE_DIR (/home/whitehost/spv/)
        self.base_dir = Path(settings.BASE_DIR)
        
        # Pathing relative to project root
        self.source_dir = self.base_dir / "contracts"
        self.artifacts_dir = self.base_dir / "artifacts"
        
        # Ensure the artifacts directory exists
        self.artifacts_dir.mkdir(exist_ok=True)

    def _compile_if_needed(self, contract_name):
        vy_file = self.source_dir / f"{contract_name}.vy"
        
        # This assertion will now pass because base_dir is exactly /home/whitehost/spv/
        assert str(vy_file) == f"/home/whitehost/spv/contracts/{contract_name}.vy"
        
        abi_file = self.artifacts_dir / f"{contract_name}.abi"
        bin_file = self.artifacts_dir / f"{contract_name}.bin"

        if not vy_file.exists():
            raise FileNotFoundError(f"🔥 Source file {vy_file} not found. Cannot compile.")

        # Trigger compilation if artifacts are missing
        if not abi_file.exists() or not bin_file.exists():
            print(f"🛠️  Compiling {contract_name}.vy...")
            
            try:
                # 1. Generate ABI
                abi_cmd = ["vyper", "-f", "abi", str(vy_file)]
                abi_data = subprocess.check_output(abi_cmd).decode("utf-8")
                abi_file.write_text(abi_data)

                # 2. Generate Bytecode (Bin)
                bin_cmd = ["vyper", "-f", "bytecode", str(vy_file)]
                bin_data = subprocess.check_output(bin_cmd).decode("utf-8")
                bin_file.write_text(bin_data)
                
                print(f"✅ Compilation finished: {contract_name}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Vyper compilation failed for {contract_name}")
                raise e

    def get_or_deploy(self, contract_name="RWALite"):
        if networks.active_provider:
            self.network_name = networks.active_provider.network.name.upper()
        
        env_key = f"ADDR_{contract_name.upper()}_{self.network_name}"
        existing_address = os.getenv(env_key)
        
        if existing_address:
            abi_file = self.artifacts_dir / f"{contract_name}.abi"
            bin_file = self.artifacts_dir / f"{contract_name}.bin"

            with open(abi_file, "r") as f:
                abi_list = json.loads(f.read())
            
            # 2. Create the Type (This avoids triggering the compiler)
            rwa_type = ContractType(abi=abi_list, contractName=contract_name)

            print(f"✅ {contract_name} found at {existing_address}")
            return Contract(existing_address, contract_type=rwa_type)
        
        self._compile_if_needed(contract_name)

        print(f"🚀 {contract_name} not found on {self.network_name}. Starting deployment...")
        return self._deploy_fresh(contract_name, env_key)

    def _deploy_fresh(self, contract_name, env_key):
        # Already ensured existence in _compile_if_needed
        abi_path = self.artifacts_dir / f"{contract_name}.abi"
        bin_path = self.artifacts_dir / f"{contract_name}.bin"

        with open(abi_path, "r") as f:
            abi = json.load(f)
        
        bytecode = bin_path.read_text().strip()
        if not bytecode.startswith("0x"):
            bytecode = f"0x{bytecode}"

        rwa_type = ContractType(
            abi=abi, 
            deploymentBytecode={"bytecode": bytecode}, 
            contractName=contract_name
        )

        payment_token = os.getenv(f"{self.network_name}_USDC_ADDRESS")
        if not payment_token:
            raise ValueError(f"Missing {self.network_name}_USDC_ADDRESS in .env")

        # Randomized symbol for unique deployment identifiers
        ticker = f"XCCAP-{random.randint(1000, 9999)}"

        new_contract = self.admin.deploy(
            rwa_type, 
            f"XC Capital {contract_name} Note", 
            ticker, 
            payment_token
        )

        set_key(".env", env_key, new_contract.address)
        print(f"💾 Saved {contract_name} to {env_key}")
        
        return new_contract


factory = RWAFactory(get_unlocked_admin())


# --- FOR BATCH CALLS ---
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