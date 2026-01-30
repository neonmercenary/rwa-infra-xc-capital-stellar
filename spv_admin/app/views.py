from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from .blockchain.ipfs import hybrid_ipfs_upload
from django.contrib import messages
from decimal import Decimal
import json, random
import os, csv, asyncio
from ape import networks
from eth_utils import decode_hex
from django.conf import settings
from .blockchain.client import (
    NetworkConfig, 
    get_multicall_yields, 
    factory, 
    get_unlocked_admin
)
from ape import networks 
from app.services.helpers import (
    create_loan_metadata,
    calculate_metadata_hash,
    generate_rwa_ids
)
from .models import (
    Loan,
    TokenizationSpec,
    Investor,
    InvestorPosition,
    CashflowHistory,
)

# WILL IMPLEMENT SOROBAN SYNTAX 
from .blockchain.functions import (
    create_token_onchain,
    deposit_dividends_onchain,
    transfer_rwa_token,
    create_tranche_token_onchain,
    deposit_tranche_dividend_onchain
    
)
from django.conf import settings


BASE = settings.BASE_DIR
OWNER = get_unlocked_admin()
get_contract_type = lambda loan: "RWATranchDemo" if loan.tranches else "RWALite" # WILL IMPLEMENT SOROBAN SYNTAX 



# -----------------------
# SPV Views (admin)
# -----------------------
@staff_member_required
def spv_dashboard(request):
    loans = Loan.objects.all()
    total_principal = sum(l.principal for l in loans)
    total_interest = sum(l.monthly_interest for l in loans)

    return render(
        request,
        "spv/dashboard.html",
        {
            "loans": loans,
            "total_principal": total_principal,
            "total_interest": total_interest,
        },
    )


@staff_member_required
def spv_loans_list(request):
    loans = Loan.objects.all().order_by("-created_at")
    return render(request, "spv/loans.html", {"loans": loans})


@staff_member_required
def spv_loan_add(request):
    if request.method == "POST":
        loan_id = request.POST.get("loan_id")
        title = request.POST.get("title")
        borrower = request.POST.get("borrower")
        principal = Decimal(request.POST.get("principal"))
        annual_interest_rate = Decimal(request.POST.get("annual_interest_rate"))
        term_months = int(request.POST.get("term_months"))
        maturity_date = request.POST.get("maturity_date")
        unit_price_usdc = Decimal(request.POST.get("unit_price_usdc"))
        total_slices = int(request.POST.get("total_slices"))
        monthly_payment = Decimal(request.POST.get("monthly_payment"))
        tranches = request.POST.get("tranches") == "true"
        tokenization_id = request.POST.get("tokenization_spec")
        if tokenization_id:
            tokenization_spec = TokenizationSpec.objects.get(id=tokenization_id)
        else:
            tokenization_spec = None

        Loan.objects.create(
            loan_id=loan_id,
            title=title,
            borrower=borrower,
            principal=principal,
            annual_interest_rate=annual_interest_rate,
            term_months=term_months,
            unit_price_usdc=unit_price_usdc,
            total_slices=total_slices,
            maturity_date=maturity_date,
            monthly_payment=monthly_payment,
            tranches=tranches,
            tokenization_spec=tokenization_spec,
        )

        messages.success(request, "Loan added successfully.")
        return redirect("rwa:spv_dashboard")

    all_specs = TokenizationSpec.objects.all()
    context = {
        "tokenization_specs": all_specs,
    }
    return render(request, "spv/add_loan.html", context)


@staff_member_required
def spv_loan_edit(request, loan_id):
    # Fetch the existing loan or return 404
    loan = get_object_or_404(Loan, loan_id=loan_id)

    if request.method == 'POST':
        # Update fields from POST data
        loan.loan_id = request.POST.get('loan_id')
        loan.title = request.POST.get('title')
        loan.borrower = request.POST.get('borrower')
        loan.principal = request.POST.get('principal')
        loan.annual_interest_rate = request.POST.get('annual_interest_rate')
        loan.term_months = request.POST.get('term_months')
        loan.monthly_payment = request.POST.get('monthly_payment')
        loan.start_date = request.POST.get('start_date')
        loan.maturity_date = request.POST.get('maturity_date')
        loan.status = request.POST.get('status')
        loan.total_slices = request.POST.get('total_slices')
        loan.unit_price_usdc = request.POST.get('unit_price_usdc')
        loan.token_contract = request.POST.get('token_contract')
        loan.metadata_cid = request.POST.get('metadata_cid')
        loan.tranches = request.POST.get("tranches") == "true"   # only this works
        tokenization_spec = request.POST.get("tokenization_spec")
        if tokenization_spec:
            loan.tokenization_spec = TokenizationSpec.objects.get(id=tokenization_spec)
        else:
            loan.tokenization_spec = None
        loan.save()
        return redirect('rwa:spv_dashboard')

    # For dates, we need them in YYYY-MM-DD format for HTML5 date inputs
    context = {
        'loan': loan,
        'start_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else '',
        'maturity_date': loan.maturity_date.strftime('%Y-%m-%d') if loan.maturity_date else '',
    }
    return render(request, 'spv/edit_loan.html', context)


@staff_member_required
def spv_loan_delete(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    loan.delete()
    messages.success(request, "Loan deleted successfully.")
    return redirect("rwa:spv_dashboard")


@staff_member_required
def spv_loan_detail(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    positions = InvestorPosition.objects.filter(loan=loan)
    cashflows = CashflowHistory.objects.filter(loan=loan)
    slices_distributed = sum(pos.slices_owned for pos in positions)

    return render(
        request,
        "spv/loan_detail.html",
        {
            "loan": loan,
            "positions": positions,
            "cashflows": cashflows,
            "slices_distributed": slices_distributed,
        },
    )


@staff_member_required
def review_tokenization(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    
    # Generate the same metadata payload we will send to IPFS
    metadata_payload = create_loan_metadata(loan)
    fingerprint = calculate_metadata_hash(metadata_payload)
    
    context = {
        'loan': loan,
        'metadata_json': json.dumps(metadata_payload, indent=4),
        'fingerprint': fingerprint,
    }
    return render(request, 'spv/review_tokenization.html', context)


@staff_member_required
def spv_tokenize_loan(request, loan_id):
    if request.method != "POST":
        return redirect('rwa:review_tokenization', loan_id=loan_id)
    
    
    loan = get_object_or_404(Loan, loan_id=loan_id)

    if loan.tokenized:
        messages.info(request, "Loan already tokenized.")
        return redirect("rwa:spv_loan_detail", loan_id=loan_id)

    try:
        # 1. IPFS Logic (Off-chain, no Ape connection needed yet)
        metadata_payload = create_loan_metadata(loan)
        ipfs_cid = asyncio.run(hybrid_ipfs_upload(metadata_payload))
        ipfs_uri = f"ipfs://{ipfs_cid}"
        
        fingerprint_hex = calculate_metadata_hash(metadata_payload)
        fingerprint_bytes = decode_hex(fingerprint_hex)

        # 2. Blockchain Logic (Wrapped in the correct context)
        # Use networks.parse_network_choice for modern Ape versions
        print(f"🌐 Connecting to blockchain network... {settings.DEFAULT_NETWORK}")
        with networks.parse_network_choice(settings.DEFAULT_NETWORK):
            # Get the contract instance
            print("Current working directory:", os.getcwd())
            master_contract = factory.get_or_deploy(get_contract_type(loan))
            print(f"✅ Connected to blockchain network. Using owner account: {OWNER}")
            print(f"🔗 Using Master Contract at: {master_contract.address}")
            
            if not master_contract:
                raise Exception("Could not connect to or deploy Master Contract.")
            
            parent_id, senior_id, junior_id = generate_rwa_ids()
            if loan.tranches:
                print("🏗️ Tokenizing as Tranche-based loan...")
                spec = loan.tokenization_spec

                senior_slices = int(loan.total_slices * spec.senior_pct / 100)
                junior_slices = int(loan.total_slices * spec.junior_pct / 100)

                senior_total = loan.principal * (1 + spec.senior_coupon_pct / 100)
                senior_cap   = int(senior_total / senior_slices * 10**6)
                print(f"- Senior slices: {senior_slices} at cap {senior_cap} USDC each")


                # WILL IMPLEMENT SOROBAN SYNTAX 
                receipt = create_tranche_token_onchain(
                    contract_addr=master_contract.address,
                    parent_id=parent_id,
                    senior_id=senior_id,
                    junior_id=junior_id,
                    senior_supply=senior_slices,
                    junior_supply=junior_slices,
                    senior_price=int(loan.unit_price_usdc * 10**6),
                    junior_price=int(loan.unit_price_usdc * 10**6),
                    senior_cap=senior_cap,
                    uri=ipfs_uri,
                    fingerprint=fingerprint_bytes
                )
            else:
                print("🏗️ Tokenizing as Single-tranche loan...")
                # Single-tranche tokenization
                receipt = create_token_onchain(
                        contract_addr=master_contract.address, # Use .address from the object
                        token_id=(int(loan.id) * parent_id),
                        initial_supply=int(loan.total_slices),
                        price_usdc=int(loan.unit_price_usdc * 10**6),
                        uri=ipfs_uri,
                        fingerprint=fingerprint_bytes
                    )
                
                # Save the address for the DB update
            contract_address = master_contract.address

            # 3. Update DB (After the 'with' block confirms success)
            loan.tokenized = True
            loan.token_contract = contract_address
            loan.token_id = parent_id
            loan.senior_id = senior_id if loan.tranches else None
            loan.junior_id = junior_id if loan.tranches else None
            loan.metadata_cid = ipfs_cid
            loan.metadata_hash = fingerprint_hex
            loan.save()

            messages.success(request, f"Loan tokenized! Contract: {contract_address}")
            
    except Exception as e:
        import traceback
        print(traceback.format_exc()) # See the real error in your terminal
        messages.error(request, f"Tokenization failed: {e}")
        
    return redirect("rwa:spv_loan_detail", loan_id=loan_id)


@staff_member_required
def spv_distribute_payment(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    positions = InvestorPosition.objects.filter(loan=loan)
    total_interest = Decimal(loan.monthly_interest) 
    amount_in_units = int(total_interest * 1000000) # USDC 6 decimals

    try:
        with networks.parse_network_choice(settings.DEFAULT_NETWORK):
            # 1. Move the actual USDC on-chain

            if loan.tranches:                
                print("⚠️ Distributing dividends to Tranche loan holders...")
                # For tranche loans, use multicall to get yields
                print(f"Total yield to distribute: {total_interest} units")

                # WILL IMPLEMENT SOROBAN SYNTAX 
                receipt = deposit_tranche_dividend_onchain(
                    contract_addr=loan.token_contract,
                    target_id=loan.senior_id,
                    amount_usdc_units=amount_in_units,
                    usdc_address=settings.USDC_ADDRESS,
                )
                tx_hash = receipt.txn_hash

            else:
                receipt = deposit_dividends_onchain(
                    contract_addr=loan.token_contract,
                    token_id=loan.token_id,
                    amount_usdc_units=amount_in_units,
                    usdc_address=settings.USDC_ADDRESS,
                )
                tx_hash = receipt.txn_hash

            # 2. Update Database (only if blockchain succeeded)
            with transaction.atomic():
                for pos in positions:
                    # Calculate share: (investor_slices / total_slices) * total_interest
                    share = (Decimal(pos.slices_owned) / Decimal(loan.total_slices)) * total_interest
                    
                    # Update investor balance
                    pos.balance_due += share
                    pos.save()

                    # Create audit trail record for THIS investor
                    CashflowHistory.objects.create(
                        loan=loan,
                        investor=pos.investor,
                        amount=share,
                        tx_hash=tx_hash,
                        description=f"Monthly interest distribution for {loan.loan_id}",
                    )

        messages.success(request, f"Yield of ${total_interest} distributed to {positions.count()} holders.")
        
    except Exception as e:
        import traceback
        print(f"DEBUG: Error Type: {type(e)}")
        print(traceback.format_exc()) # THIS will tell you exactly which line in views.py failed
        messages.error(request, f"Distribution Failed: {str(e)}")

    return redirect("rwa:spv_loan_detail", loan_id=loan_id)



@staff_member_required
def investor_list(request):
    investors = Investor.objects.all()
    return render(request, "spv/investor_list.html", {"investors": investors})


@staff_member_required
def investor_view(request, investor_id):
    investor = get_object_or_404(Investor, id=investor_id)
    return render(request, "spv/investor_view.html", {"investor": investor})


@staff_member_required
def spv_investor_positions(request, investor_id):
    # Fetch investor
    investor = get_object_or_404(Investor, id=investor_id)

    # Fetch all positions (investor-loan relationships)
    positions = InvestorPosition.objects.filter(investor=investor).select_related("loan")
    
    # Calculate the total yield across all positions (if needed)
    total_yield = sum([pos.accrued_yield() for pos in positions])

    return render(request, "spv/investor_positions.html", {
        "investor": investor,
        "positions": positions,
        "total_yield": total_yield,
    })



@staff_member_required
def add_investor(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        wallet_address = request.POST.get("wallet_address")  # keep as string

        investor, _ = Investor.objects.get_or_create(
            email=email,
            wallet_address=wallet_address,
            defaults={"name": name},
        )

        messages.success(request, "Investor added successfully.")

    return render(request, "spv/add_investor.html")


from django.db import transaction

@staff_member_required
def spv_create_position(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    investors = Investor.objects.all()

    if request.method == "POST":
        investor_id = request.POST["investor"]
        slices_to_add = int(Decimal(request.POST["slices"])) # The "Delta"
        investor = get_object_or_404(Investor, id=investor_id)

        if slices_to_add <= 0:
            messages.error(request, "Units must be positive")
            return redirect("rwa:create_investor_position", loan_id=loan.loan_id)

        try:
            # 1️⃣ Execute the On-Chain Mint (MINT ONLY THE NEW SLICES)
            # We call the 'mint' function we kept in RWALite.vy
            # WILL IMPLEMENT SOROBAN SYNTAX 
            with networks.parse_network_choice(settings.DEFAULT_NETWORK):
                
                tx = transfer_rwa_token(
                    contract_addr=loan.token_contract,
                    to_address=investor.wallet_address,
                    token_id=loan.token_id if not loan.tranches else loan.senior_id,
                    amount=slices_to_add, # <--- MINT ONLY THE DELTA
                )

                # 2️⃣ Verify and Update Local DB atomically
                with transaction.atomic():
                    pos, created = InvestorPosition.objects.get_or_create(
                        investor=investor,
                        loan=loan,
                        defaults={"slices_owned": 0}
                    )
                    
                    # Update the record
                    pos.slices_owned += slices_to_add
                    pos.tx_hash = f"0x{tx.txn_hash}" if not tx.txn_hash.startswith("0x") else tx.txn_hash
                    pos.save()

            messages.success(request, f"Successfully minted {slices_to_add} slices for {investor.name}.")
            return redirect("rwa:spv_loan_detail", loan_id=loan.loan_id)

        except Exception as e:
            messages.error(request, f"Blockchain Error: {str(e)}")
            # If blockchain fails, DB remains unchanged because of the 'with' block
    
    return render(request, "spv/create_position.html", {
        "loan": loan,
        "investors": investors,
    })
