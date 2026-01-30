# app/tasks.py
import requests, re
from celery import shared_task
from app.blockchain.ipfs import fetch_loan_metadata
from django.conf import settings
from django.db import transaction
from decimal import Decimal
from ape import networks, Contract
from .models import InvestorPosition, Loan, CashflowHistory, SyncState, Investor


def normalize_key(text):
    """Converts 'Maturity Date' to 'maturity_date'."""
    return re.sub(r'\s+', '_', text.strip()).lower()

def get_trait(attributes, trait_name, default=None):
    """Finds a 'trait_type' in the attributes list and returns its 'value'."""
    for attr in attributes:
        if normalize_key(attr.get("trait_type")) == normalize_key(trait_name):
            print(f"Found trait {trait_name}: {attr.get('value')}")
            return attr.get("value", default)
    return default

def get_clean_cid(uri):
    '''Helper to handle ipfs:// prefix'''
    if uri.startswith("ipfs://"):
        return uri.replace("ipfs://", "")
    return uri



from datetime import timedelta, date
@shared_task(bind=True, max_retries=3)
def sync_blockchain_events(self):
    state, _ = SyncState.objects.get_or_create(key="hq_master_sync")
    
    # NEW ROUTESCAN STRUCTURE
    # Base URL for Avalanche Fuji (43113)
    api_url = "https://api.routescan.io/v2/network/testnet/evm/43113/etherscan/api"
    
    params = {
        "module": "account",
        "action": "txlist",
        "address": settings.MASTER_RWA_ADDRESS,
        "startblock": state.last_synced_block + 1,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": "placeholder" # Routescan free tier accepts any string here
    }
    
    try:
        response = requests.get(api_url, params=params)
        data = response.json()
        
        # Routescan returns "1" for success, same as Etherscan
        if data.get("status") != "1":
            return f"No new transactions or API error: {data.get('message')}"

        tx_list = data.get("result", [])

    except Exception as e:
        return f"Error fetching transactions: {str(e)}"
    
    # 2. Process with Ape (Surgical Verification)
    with networks.parse_network_choice(settings.DEFAULT_NETWORK):
        rwa_contract = Contract(settings.MASTER_RWA_ADDRESS)
        
        for tx in tx_list:
            receipt = networks.active_provider.get_receipt(tx['hash'])
            print(f"Fetched receipt for tx: {tx['hash']}, receipt status: {receipt.status}")
            if receipt.status != 1: continue
            print(f"Processing tx: {tx['hash']} with {len(receipt.events)} events")

            for event in receipt.events:
                # --- LOGIC A: MINTING (createToken) ---
                if event.event_name == "TokenCreated":
                    print(f"TokenCreated event for ID: {event.id}")
                    on_chain_hash = event.fingerprint.hex()
                    Loan.objects.update_or_create(
                        token_id=event.id,
                        defaults={"tokenized": True, "status": "performing", "metadata_hash": on_chain_hash}
                    )

                elif event.event_name == "TransferSingle":
                    # 1. THE MINT CASE (New Loan/Asset Creation)
                    if event.from_ == "0x0000000000000000000000000000000000000000":
                        print(f"MINT: Token {event.id} created for {event.to}")
                        
                        # Metadata and Loan Creation
                        token_cid = get_clean_cid(rwa_contract.tokenURI(event.id))
                        meta = fetch_loan_metadata(token_cid)
                        attrs = meta.get("attributes", [])
                        
                        loan_id = meta.get("name", "").replace("Loan ", "") or str(event.id)
                        # 1.  Is there already a Loan with this institutional ID?
                        try:
                            loan = Loan.objects.get(loan_id=loan_id)
                            created = False
                        except Loan.DoesNotExist:
                            loan = None
                            created = True

                        # 2.  Build the values we want to set
                        defaults = {
                            "tokenized": True,
                            "status": "performing",
                            "metadata_cid": token_cid,
                            "title": meta.get("description", f"Loan #{event.id}"),
                            "principal": Decimal(get_trait(attrs, "Principal", "0")),
                            "annual_interest_rate": Decimal(get_trait(attrs, "APR", "5.0")),
                            "unit_price_usdc": Decimal(get_trait(attrs, "Unit Price USDC", "1.0")),
                            "total_slices": int(get_trait(attrs, "Total Slices", 100)),
                            "term_months": int(get_trait(attrs, "Term Months", 12)),
                            "borrower": get_trait(attrs, "Borrower", "Unknown"),
                            "token_contract": rwa_contract.address,
                            "maturity_date": get_trait(attrs, "Maturity Date"),
                            "monthly_payment": get_trait(attrs, "Monthly Payment", "0"),
                            "token_id": event.id,          # in case we are moving the token to this row
                            "metadata_hash": get_trait(attrs, "Metadata Hash", ""),
                        }

                        # 3.  Create or update
                        if created:
                            loan = Loan.objects.create(loan_id=loan_id, **defaults)
                        else:
                            for key, value in defaults.items():
                                setattr(loan, key, value)
                            loan.save()
                        # Handle the Receiver (The Investor getting the newly minted slices)
                        if event.to in settings.ADMIN_ADDRESSES: pass
                        else:
                            receiver, _ = Investor.objects.get_or_create(
                                wallet_address=event.to, 
                                defaults={"name": "Initial Investor"}
                            )
                            
                            with transaction.atomic():
                                pos, _ = InvestorPosition.objects.get_or_create(
                                    investor=receiver, 
                                    loan=loan, 
                                    defaults={"slices_owned": 0}
                                )
                                pos.slices_owned += Decimal(str(event.value))
                                pos.save()

                    # 2. THE SECONDARY TRANSFER CASE (Sale or Transfer between users)
                    else:
                        print(f"TRANSFER: Token {event.id} moving from {event.from_} to {event.to}")
                        loan = Loan.objects.get(token_id=event.id)
                        
                        with transaction.atomic():
                            # A. Subtract from Sender
                            sender, _ = Investor.objects.get_or_create(wallet_address=event.from_.lower())
                            sender_pos = InvestorPosition.objects.get(investor=sender, loan=loan)
                            sender_pos.slices_owned -= Decimal(str(event.value))
                            sender_pos.save()

                            # B. Add to Receiver
                            receiver, _ = Investor.objects.get_or_create(wallet_address=event.to.lower())
                            receiver_pos, _ = InvestorPosition.objects.get_or_create(
                                investor=receiver, loan=loan, defaults={"slices_owned": 0}
                            )
                            receiver_pos.slices_owned += Decimal(str(event.value))
                            receiver_pos.save()


               # --- LOGIC C: YIELD ---
                elif event.event_name == "DividendsDeposited":
                    loan = Loan.objects.filter(token_id=event.tokenId).first()
                    if not loan or loan.total_slices <= 0:
                        print(f"Skipping: Loan {event.tokenId} not found or 0 slices.")
                        continue

                    actual_amount = Decimal(event.amount) / Decimal(10**6) # USDC Scale
                    
                    with transaction.atomic():
                        for pos in InvestorPosition.objects.filter(loan=loan):
                            # MULTIPLY FIRST: (Amount * Slices) / Total
                            share = (actual_amount * Decimal(pos.slices_owned)) / Decimal(loan.total_slices)
                            share = share.quantize(Decimal("0.000001")) # Round to 6 decimals
                            
                            # COMPOSITE HASH: Matches SPV side exactly
                            unique_id = f"{tx['hash']}"

                            # update_or_create prevents the double-credit bug
                            obj, created = CashflowHistory.objects.update_or_create(
                                tx_hash=unique_id,
                                defaults={
                                    "loan": loan,
                                    "investor": pos.investor,
                                    "amount": share,
                                    "description": f"Yield Dist for Block {tx['blockNumber']}"
                                }
                            )
                            
                            # Only add to balance if this is the FIRST time we see this record
                            if created:
                                pos.balance_due += share
                                pos.save()

            # Save progress block-by-block
            state.last_synced_block = int(tx['blockNumber'])
            state.save()
    
    return f"Processed {len(tx_list)} transactions."