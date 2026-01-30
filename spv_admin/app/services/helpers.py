#! rwa/app/services/helpers.py
import json, hashlib
from django.conf import settings
from decimal import Decimal 

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)  # Or str(obj) if you want to keep exact precision
        return super(DecimalEncoder, self).default(obj)

import time
import random

def generate_rwa_ids():
    """
    Generates a triplet of IDs (Parent, Senior, Junior).
    Uniqueness is guaranteed by millisecond precision + 3 random digits.
    """
    # 1. Get current time in milliseconds
    # Example: 1705929881123
    millis = int(time.time() * 1000)
    
    # 2. Add 3 digits of randomness to prevent collisions if 
    # two loans are generated in the exact same millisecond.
    # Example: 1705929881123 + 456 = 1705929881123456
    entropy = random.randint(100, 999)
    parent_id = int(f"{millis}{entropy}")
    
    # 3. Create Suffixes for tranches
    senior_id = int(f"{parent_id}01")
    junior_id = int(f"{parent_id}02")

    return parent_id, senior_id, junior_id



def create_loan_metadata(loan) -> dict:
    metadata = {
        "name": f"Loan {loan.loan_id}",
        "description": f"Private Credit RWA - ${loan.principal} {loan.title}",
        "external_url": (
            f"https://" if not settings.DEBUG else "http://"
        ) + settings.SITE_BASE_URL + f"/loan/{loan.loan_id}",
        "attributes": [
            {"trait_type": "Principal", "value": f"{loan.principal:.2f}", "display_type": "number"},
            {"trait_type": "APR", "value": f"{loan.annual_interest_rate:.2f}", "display_type": "percentage"},
            {"trait_type": "Unit Price USDC", "value": f"{loan.unit_price_usdc:.2f}", "display_type": "number"},
            {"trait_type": "Term Months", "value": int(loan.term_months), "display_type": "number"},
            {"trait_type": "Total Slices", "value": int(loan.total_slices), "display_type": "number"},
            {"trait_type": "Monthly Payment", "value": f"{loan.monthly_payment:.2f}", "display_type": "number"},
            {"trait_type": "Maturity Date", "value": loan.maturity_date.isoformat(), "display_type": "date"},
            {"trait_type": "Start Date", "value": loan.start_date.isoformat(), "display_type": "date"},
            {"trait_type": "Borrower", "value": str(loan.borrower), "display_type": "string"},
            {"trait_type": "Asset Class", "value": "Private Credit"},
        ],
    }

    if loan.tranches:
        spec = loan.tokenization_spec
        metadata["attributes"].extend([
            {"trait_type": "Structure", "value": "Tranche"},
            {"trait_type": "Senior %", "value": f"{spec.senior_pct:.2f}", "display_type": "percentage"},
            {"trait_type": "Junior %", "value": f"{spec.junior_pct:.2f}", "display_type": "percentage"},
            {"trait_type": "Senior Yield", "value": int(spec.senior_coupon_pct), "display_type": "number"},
            {"trait_type": "Senior Cap Method", "value": spec.senior_cap_method, "display_type": "string"},
        ])

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