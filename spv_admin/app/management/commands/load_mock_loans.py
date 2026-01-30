from django.core.management.base import BaseCommand
from app.models import Loan, TokenizationSpec
from decimal import Decimal
import uuid, random
from datetime import date, timedelta

class Command(BaseCommand):
    help = "Create 10 fake loans (half tranched) for quick testing"

    def handle(self, *args, **opts):
        spec, _ = TokenizationSpec.objects.get_or_create(
            name="70-30-8pct",
            defaults=dict(
                senior_pct=Decimal("70.00"),
                junior_pct=Decimal("30.00"),
                senior_coupon_pct=Decimal("8.00"),
                senior_cap_method="simple",
            ),
        )

        for i in range(3):
            is_tranche = True
            principal = 30000
            Loan.objects.create(
                loan_id=f"MOCK-{uuid.uuid4().hex[:6].upper()}",
                title=f"Mock Loan {i+1}",
                borrower=f"Borrower-{i+1}",
                principal=principal,
                annual_interest_rate=Decimal("10"),
                term_months=12,
                start_date=date.today(),
                maturity_date=date.today() + timedelta(days=360),
                monthly_payment=Decimal(str(250)),
                total_slices=100,
                unit_price_usdc=Decimal("300.00"),
                tranches=is_tranche,
                tokenization_spec=spec if is_tranche else None,
                status="performing",
            )
        self.stdout.write(self.style.SUCCESS("10 mock loans created"))