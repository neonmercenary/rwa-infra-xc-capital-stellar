import json
from .client import factory
from ape import Contract
from ethpm_types import ContractType
from ape import accounts, networks
from ape.utils import ZERO_ADDRESS
from decimal import Decimal

#   THIS FILE CONTAINS THE ON-CHAIN INTERACTION LOGIC FOR THE RWA TRANCHING CONTRACTS
#   SOROBAN CURRENTLY BEING INTEGRATED. 



# --- Configuration ---
# Ape handles the 'OWNER' via: ape accounts load <alias>
# Or via environment variables for the grant/MVP
DEPLOYER = accounts.load("spv_admin")
# Minimal ABI so we don't need to call Etherscan/Snowtrace
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


def get_contract(address=None):
    return factory.get_or_deploy("RWATrancheDemo") if address is None else Contract(address)


def create_token_onchain(contract_addr, token_id, initial_supply, price_usdc, uri, fingerprint):
    c = get_contract(contract_addr)
    
    # Ape handles nonce and gas automatically
    receipt = c.createToken(
        token_id, 
        initial_supply, 
        price_usdc,
        uri, 
        fingerprint, 
        sender=DEPLOYER
    )
    return receipt

def create_tranche_token_onchain(
    contract_addr, 
    parent_id, 
    senior_id, 
    junior_id, 
    senior_supply, 
    junior_supply, 
    senior_price, 
    junior_price, 
    senior_cap, 
    uri, 
    fingerprint
):
    """
    Deploys a linked Senior/Junior tranche pair under a Parent ID.
    senior_cap: The max payout (Principal + Interest) per Senior share.
    """
    c = get_contract(contract_addr)
    
    print(f"🏗️ Creating Tranche Loan: Parent({parent_id}) -> Senior({senior_id}), Junior({junior_id})")
    
    # Calls the new 'createTrancheToken' function with 10 arguments
    receipt = c.createTrancheToken(
        parent_id,
        senior_id,
        junior_id,
        senior_supply,
        junior_supply,
        senior_price,
        junior_price,
        senior_cap,
        uri,
        fingerprint,
        sender=DEPLOYER
    )
    
    return receipt


def deposit_dividends_onchain(contract_addr, token_id, amount_usdc_units, usdc_address):
    """
    Step 1: Approve the RWA contract to spend SPV's USDC.
    Step 2: Deposit the USDC into the RWA contract for distribution.
    """
    c = get_contract(contract_addr)
    # Use at() to get the USDC contract instance
    usdc = Contract(usdc_address, abi=ERC20_ABI)
    
    print(f"🛡️ Approving exact amount: {amount_usdc_units} units")
    usdc.approve(contract_addr, amount_usdc_units, sender=DEPLOYER)
    
    print("🚀 Executing Deposit...")
    receipt = c.depositDividends(token_id, amount_usdc_units, sender=DEPLOYER)
    
    # Return the receipt object directly so Ape can read the logs
    return receipt

def deposit_tranche_dividend_onchain(contract_addr, target_id, amount_usdc_units, usdc_address):
    """
    Deposits USDC into the Senior ID. The Vyper contract then:
    1. Fills Senior holders up to their cap.
    2. Spills remaining funds over to the Junior sibling ID.
    """
    c = Contract(contract_addr)
    usdc = Contract(usdc_address)
    admin_bal = usdc.balanceOf.call(DEPLOYER.address, sender=DEPLOYER)


    # HARD CHECK: Stop before we waste gas on a revert
    # if admin_bal < amount_usdc_units:
    #     raise ValueError(
    #         f"INSUFFICIENT FUNDS: Admin wallet needs {amount_usdc_units / 10**6} USDC "
    #         f"but only has {admin_bal / 10**6}. Please fund the account."
    #     )
    

    # --- PRE-FLIGHT CHECKS ---
    sibling_id = c.sibling(target_id)
    total_supply = c.tokenSupply(target_id)
    print(f"🔍 Pre-Flight Checks: Target ID {target_id} has Sibling ID {sibling_id} ")
    
    if sibling_id == 0:
        raise ValueError(f"❌ REVERT PREVENTED: ID {target_id} has no sibling. "
                         f"You must target the SENIOR ID for waterfall deposits.")
    
    if total_supply == 0:
        raise ValueError(f"❌ REVERT PREVENTED: Senior ID {target_id} has 0 supply. "
                         f"You cannot deposit dividends if no tokens have been issued.")

    # --- EXECUTION ---
    print(f"🛡️ Approving {amount_usdc_units / 10**6} USDC...")
    usdc.approve(contract_addr, amount_usdc_units, sender=DEPLOYER)
    
    print(f"🌊 Executing Waterfall Deposit into Senior ID {target_id}...")
    try:
        receipt = c.depositDividends(target_id, amount_usdc_units, sender=DEPLOYER)
        print(f"✅ Waterfall complete: {receipt.txn_hash}")
        return receipt
    
    except Exception as e:
        print(f"🔥 Blockchain Revert: {e}")
        raise e

def transfer_rwa_token(contract_addr, to_address, token_id, amount):
    """
    Tranche version (Replaces directly minting)
    Moves tokens from the Admin (who received them at creation) to the Investor.
    This triggers the magnifiedDividendCorrections in Vyper automatically.
    """
    c = Contract(contract_addr)
    
    print(f"📦 Transferring {amount} units of ID {token_id} to {to_address}...")
    
    # In your Vyper contract, safeTransferFrom is limited to the owner for MVP sanity
    # DEPLOYER must be the account that called createTrancheToken
    receipt = c.safeTransferFrom(
        DEPLOYER.address, # from
        to_address,       # to
        token_id,         # id
        amount,           # value
        sender=DEPLOYER
    )
    
    print(f"✅ Transfer confirmed: {receipt.txn_hash}")
    return receipt

def buy_tokens(contract_addr, buyer_account, token_id, units):
    """
    If buyer_account is an Ape 'Account' object, this is one line.
    """
    c = get_contract(contract_addr)
    # The buyer must have approved USDC already
    return c.buy(token_id, units, sender=buyer_account)

def withdraw_dividend_onchain(contract_addr, token_id, user_account):
    c = get_contract(contract_addr)
    return c.withdrawDividend(token_id, sender=user_account)

def get_withdrawable(contract_addr, token_id, account_addr):
    c = get_contract(contract_addr)
    # '.call' is used for @view functions in Ape
    return c.withdrawableDividendOf(token_id, account_addr)

def mint_position_onchain(contract_addr, investor_wallet, token_id, units):
    c = get_contract(contract_addr)
    return c.mint(investor_wallet, token_id, units, sender=DEPLOYER)

def check_balance(contract_addr, account_addr, token_id):
    c = get_contract(contract_addr)
    return c.balanceOf(account_addr, token_id)

def get_total_slices(contract_addr, token_id):
    c = get_contract(contract_addr)
    return c.totalSlices(token_id)

