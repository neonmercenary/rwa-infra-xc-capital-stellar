#! rwa/app/services/helpers.py
import json, hashlib
from django.conf import settings
from decimal import Decimal 

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)  # Or str(obj) if you want to keep exact precision
        return super(DecimalEncoder, self).default(obj)


def create_loan_metadata(loan) -> dict:
    """
    Standardizes all critical loan terms into a single JSON object.
    Any change to these fields will break the SHA-256 integrity check.
    """
    metadata = {
        "name": f"Loan {loan.loan_id}",
        "description": f"Private Credit RWA - ${loan.principal} {loan.title}",
        "image": "ipfs://QmYourPropertyImageHash",
        "external_url": f"https://{settings.SITE_BASE_URL}/loan/{loan.loan_id}",
        "attributes": [
            # Financials (Forced to 2 decimal places for hash consistency)
            {"trait_type": "Principal", "value": "{:.2f}".format(loan.principal), "display_type": "number"},
            {"trait_type": "APR", "value": "{:.2f}".format(loan.annual_interest_rate), "display_type": "percentage"},
            {"trait_type": "Unit Price USDC", "value": "{:.2f}".format(loan.unit_price_usdc), "display_type": "number"},
            
            # Terms & Dates
            {"trait_type": "Term Months", "value": int(loan.term_months), "display_type": "number"},
            {"trait_type": "Total Slices", "value": int(loan.total_slices), "display_type": "number"},
            {"trait_type": "Maturity Date", "value": loan.maturity_date.isoformat(), "display_type": "date"},
            {"trait_type": "Start Date", "value": loan.start_date.isoformat(), "display_type": "date"},
            {"trait_type": "Monthly Payment", "value": "{:.2f}".format(loan.monthly_payment), "display_type": "number"},
            
            # Entity Info
            {"trait_type": "Borrower", "value": str(loan.borrower), "display_type": "string"},
            {"trait_type": "Asset Class", "value": "Private Credit"},
        ],
    }
    return metadata


def calculate_metadata_hash(metadata_dict):
    # Use the same encoder here so the hash matches the uploaded file!
    content = json.dumps(
        metadata_dict, 
        sort_keys=True, 
        cls=DecimalEncoder, 
        separators=(',', ':')
    ).encode('utf-8')
    return hashlib.sha256(content).hexdigest()