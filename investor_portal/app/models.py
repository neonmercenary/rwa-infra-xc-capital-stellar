from django.db import models
from decimal import Decimal
from django.utils import timezone
import requests
from app.services.helpers import (
    calculate_metadata_hash,
    create_loan_metadata
)


class Loan(models.Model):
    # 🔒 INSTITUTIONAL ANCHOR
    loan_id = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=300)
    borrower = models.CharField(max_length=200)
    principal = models.DecimalField(max_digits=18, decimal_places=2)  # UPB
    annual_interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    term_months = models.IntegerField()
    start_date = models.DateField(default=timezone.now)
    maturity_date = models.DateField()
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=50, default="performing")

    # BLOCKCHAIN
    token_contract = models.CharField(max_length=128, blank=True)
    tx_hash = models.CharField(max_length=200, blank=True, null=True)
    token_id = models.BigIntegerField(null=True, blank=True)
    total_slices = models.IntegerField(default=100)
    unit_price_usdc = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    metadata_cid = models.CharField(max_length=100, blank=True, null=True)
    metadata_hash = models.CharField(max_length=64, blank=True, null=True)

    # SANITY CHECK
    tokenized = models.BooleanField(default=False)
    synchronized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


    @property
    def ipfs_url(self):
        if self.metadata_cid:
            # You can change the gateway here if ipfs.io is slow
            return f"https://ipfs.io/ipfs/{self.metadata_cid}"
        return None
    
    @property
    def check_integrity(self):
        """The core logic for your 'Mind Blow' demo."""
        try:
            # 1. Fetch live data from IPFS
            resp = requests.get(f"https://ipfs.io/ipfs/{self.metadata_cid}", timeout=3)
            live_data = resp.json()

            # 2. Re-calculate SHA-256
            current_hash = calculate_metadata_hash(live_data)

            if self.metadata_hash != current_hash:
                print(f"DEBUG Mismatch for Loan {self.loan_id}:")
                print(f"Expected (On-Chain): {self.metadata_hash}")
                print(f"Actual (From IPFS):  {current_hash}")
                # Print the actual string being hashed to see the formatting

                print(f"String being hashed: {current_hash}")

            # 3. Compare to the Blockchain 'Truth' in our DB
            return current_hash == self.metadata_hash
        except:
            return False

    def __str__(self):
        return f"{self.loan_id} — {self.title}"

    @property
    def progress_percentage(self):
        if not self.start_date or not self.maturity_date:
            return 0
        total_days = (self.maturity_date - self.start_date).days
        days_elapsed = (timezone.now().date() - self.start_date).days
        
        if total_days <= 0: return 100
        percent = (days_elapsed / total_days) * 100
        return min(max(int(percent), 0), 100)
    

    @property
    def days_remaining(self):
        """Returns the number of days until the loan matures."""
        if not self.maturity_date:
            return 0
        
        today = timezone.now().date()
        delta = self.maturity_date - today
        
        # If the date has already passed, return 0 instead of a negative number
        return max(delta.days, 0)

    @property
    def is_matured(self):
        """Simple boolean check for maturity status."""
        return self.days_remaining == 0
    

    @property
    def monthly_interest(self) -> Decimal:
        return (self.principal * (self.annual_interest_rate / Decimal(100))) / Decimal(str(self.term_months))


class Investor(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    wallet_address = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


class InvestorPosition(models.Model):
    investor = models.ForeignKey(Investor, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    slices_owned = models.DecimalField(max_digits=12, decimal_places=6, default=0)  # e.g., 1.0 = 1 slice
    balance_due = models.DecimalField(max_digits=18, decimal_places=6, default=0)   # USDC owed to investor (accrued payouts)
    
    tx_hash = models.CharField(max_length=200, blank=True, null=True)
    last_block_synced = models.PositiveIntegerField(default=0) # Track block height

    class Meta:
        unique_together = ("investor", "loan")
        indexes = [
            models.Index(fields=['investor', 'loan']),
        ]

    def accrued_yield(self):
        # Yield calculation example: (principal * interest_rate * time) / total_slices
        loan = self.loan
        yield_amount = (loan.principal * loan.annual_interest_rate / 100) * loan.term_months / 12
        return yield_amount * (self.slices_owned / loan.total_slices)

    @property
    def ownership_percent(self):
        total = self.loan.total_slices or 100
        return (Decimal(self.slices_owned) / Decimal(total)) * Decimal(100)

    def __str__(self):
        return f"{self.investor} → {self.loan.loan_id} : {self.slices_owned}"


class SyncState(models.Model):
    '''
    The SyncState tells the future standalone worker to start from the last synced block.
    '''
    key = models.CharField(max_length=50, unique=True)
    last_synced_block = models.PositiveIntegerField(default=0)



class CashflowHistory(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    investor = models.ForeignKey(Investor, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # 🆕 Added unique=True for HQ Sync
    tx_hash = models.CharField(max_length=200, unique=True) 
    block_number = models.PositiveIntegerField(default=0, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name_plural = "Cashflow Histories"