import click
import os
import json
from ape import networks, accounts
from dotenv import set_key, find_dotenv
# This is the correct import for modern Ape
from ethpm_types import ContractType 
from ape.cli import ConnectedProviderCommand
from app.blockchain.client import NETWORK_CONFIG

# Load account outside the CLI function
OWNER = accounts.load("spv_admin")
OWNER.set_autosign(True, passphrase="heathens")
ENV_PATH = find_dotenv(filename=".env")

@click.command(cls=ConnectedProviderCommand)
def cli(network, provider):
    """Deploy the RWA Master contract using pre-compiled artifacts."""
    
    # 1. Load files
    if not os.path.exists("rwa.abi") or not os.path.exists("rwa.bin"):
        click.echo("❌ Missing rwa.abi or rwa.bin! Run 'vyper -f abi...' first.")
        return

    with open("rwa.abi", "r") as f:
        abi_list = json.loads(f.read())
    
    with open("rwa.bin", "r") as f:
        bytecode = f.read().strip()
        if not bytecode.startswith("0x"):
            bytecode = f"0x{bytecode}"

    # 2. Build the Type object (ethpm_types is what Ape uses under the hood)
    rwa_type = ContractType(
        abi=abi_list,
        deploymentBytecode={"bytecode": bytecode},
        contractName="RWALite"
    )

    # 3. Get variables
    usdc_address = os.getenv("FUJI_USDC_ADDRESS")
    click.echo(f"🚀 Deploying to {network}...")

    # THE DEPLOYMENT
    instance = OWNER.deploy(rwa_type, "RWA Master Vault", "RWAV", usdc_address)

    # NEW: WRITE TO .ENV
    env_key = f"MASTER_RWA_ADDRESS_{network.upper()}"
    set_key(ENV_PATH, env_key, instance.address)
    
    click.echo(f"✅ SUCCESS! {env_key} saved to .env: {instance.address}")