from datetime import date
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from decimal import Decimal
import json, csv
from ape import networks
from eth_utils import decode_hex
from django.conf import settings
from .blockchain.client import NetworkConfig, get_multicall_yields
from app.services.helpers import (
    calculate_metadata_hash,
)
from .models import (
    Loan,
    Investor,
    InvestorPosition,
    CashflowHistory,
)
from .blockchain.avax import (
    check_balance
)
from django.conf import settings


BASE = settings.BASE_DIR
# -----------------------
# Decorators
# -----------------------
def spv_only(view):
    return staff_member_required(view)


# -----------------------
# Public Views
# -----------------------
def public_loans_list(request):
    loans = Loan.objects.all().order_by("-created_at")
    return render(request, "public/loans.html", {"loans": loans})


def public_loan_detail(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    return render(
        request,
        "public/loan_detail.html",
        {"loan": loan, "is_verified": loan.check_integrity},
    )

def loan_metadata(request, loan_id):
    loan = get_object_or_404(Loan, loan_id=loan_id)
    token_id = loan.token_id
    meta_path = BASE / "artifacts" / "metadata" / f"{token_id}.json"
    if not meta_path.exists():
        return JsonResponse({"error": "Metadata not found"}, status=404)
    with open(meta_path, "r") as f:
        data = json.load(f)
    return JsonResponse(data)


# -----------------------
# Investor
# -----------------------
def investor_positions(request, wallet):
    # Use iexact to be case-insensitive with hex addresses
    positions_qs = InvestorPosition.objects.filter(
        investor__wallet_address__iexact=wallet
    ).select_related("loan", "investor")
    
    positions = list(positions_qs)

    # 1. Fetch the absolute truth from the Blockchain
    if positions:
        """ Fetch on-chain yields for all positions in a single multicall """
        print("Fetching on-chain yields via multicall...")
        with networks.parse_network_choice(settings.DEFAULT_NETWORK):
            raw_yields = get_multicall_yields(positions)
            for pos, raw_val in zip(positions, raw_yields):
                # Convert units to USDC (10^6)
                # We assign this to pos.onchain_yield so the template can find it
                pos.onchain_yield = Decimal(raw_val) / Decimal(1000000)
    else:
        raw_yields = []

    # 2. CSV Export Logic
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="positions_{wallet}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Loan ID", "Loan Title", "Borrower",
            "Slices Owned", "Accrued Yield (USDC)", "Maturity", "Status"
        ])
        
        for pos in positions:
            writer.writerow([
                pos.loan.loan_id,
                pos.loan.title,
                pos.loan.borrower,
                pos.slices_owned,
                f"{pos.onchain_yield:.2f}", 
                pos.loan.maturity_date,
                "Matured" if date.today() > pos.loan.maturity_date else "Active"
            ])
        return response

    # 3. Render Dashboard
    return render(request, "investor/dashboard.html", {
        "wallet": wallet, 
        "positions": positions
    })


def investor_holdings(request):
    if request.method == "POST":
        wallet = request.POST.get("wallet", None)
        return redirect("app:investor_dashboard", wallet=wallet)
    return render(request, "investor/view_holdings.html")