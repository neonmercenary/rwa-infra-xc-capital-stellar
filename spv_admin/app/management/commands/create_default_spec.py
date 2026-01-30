from django.core.management.base import BaseCommand
from app.models import TokenizationSpec

class Command(BaseCommand):
    help = "Seed the default 70-30-8 % tranche spec"

    def handle(self, *args, **opts):
        spec, created = TokenizationSpec.objects.get_or_create(
            name="70-30-8pct - Tranche Settings",
            defaults=dict(
                senior_pct=70.00,
                junior_pct=30.00,
                senior_coupon_pct=8.00,
            ),
        )
        self.stdout.write(
            self.style.SUCCESS(f"Spec '{spec.name}' created" if created else "Already exists")
        )