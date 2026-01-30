from django.core.management.base import BaseCommand
from app.models import Loan
from decimal import Decimal
from datetime import date, timedelta

MOCK = [
    {"loan_id":"LN-2026-001","title":"Brooklyn Duplex Bridge Loan","borrower":"Borrower A","principal":120000,"annual_interest_rate":10.5,"term_months":24,"monthly_payment":5650,"status":"performing","total_slices":100,"unit_price_usdc":120},
    {"loan_id":"LN-2026-002","title":"Phoenix Single-Family Rental Note","borrower":"Borrower B","principal":65000,"annual_interest_rate":11.0,"term_months":36,"monthly_payment":2206.74,"status":"performing","total_slices":100,"unit_price_usdc":65},
    {"loan_id":"LN-2026-003","title":"Atlanta Rehab Bridge","borrower":"Borrower C","principal":95000,"annual_interest_rate":13.0,"term_months":12,"monthly_payment":8450.35,"status":"late","total_slices":100,"unit_price_usdc":95},
    {"loan_id":"LN-2026-004","title":"Midwest Small Multifamily Loan","borrower":"Borrower D","principal":185000,"annual_interest_rate":9.0,"term_months":60,"monthly_payment":3814.77,"status":"performing","total_slices":100,"unit_price_usdc":185},
    {"loan_id":"LN-2026-005","title":"Seller-Financed Suburban Home","borrower":"Borrower E","principal":42000,"annual_interest_rate":12.5,"term_months":48,"monthly_payment":1111.19,"status":"performing","total_slices":42000,"unit_price_usdc":1},
]

class Command(BaseCommand):
    help = "Load mock loans for demo"

    def handle(self, *args, **options):
        for m in MOCK:
            obj, created = Loan.objects.get_or_create(
                loan_id=m["loan_id"],
                defaults={
                    "title": m["title"],
                    "borrower": m["borrower"],
                    "principal": Decimal(m["principal"]),
                    "annual_interest_rate": Decimal(m["annual_interest_rate"]),
                    "term_months": m["term_months"],
                    "maturity_date": date.today().replace(day=1) + timedelta(days=m["term_months"]*30),
                    "monthly_payment": Decimal(str(m["monthly_payment"])),
                    "status": m["status"],
                    "total_slices": m["total_slices"],
                    "unit_price_usdc": Decimal(m["unit_price_usdc"]),
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {obj.loan_id}"))
            else:
                self.stdout.write(f"Skipped {obj.loan_id} (exists)")
