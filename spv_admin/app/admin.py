from django.contrib import admin
from django.http import HttpResponse
import csv

from . import models



@admin.register(models.Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "loan_id",
        "title",
        "borrower",
        "principal",
        "status",
        "tokenized",
        "token_contract",
        "token_id",
        "positions_count",
        "slices_sold",
        "total_balance_due",
        "monthly_interest",
        "metadata_hash"
    )
    list_filter = ("status", "tokenized")
    search_fields = ("loan_id", "title", "borrower")
    readonly_fields = ("created_at", "monthly_interest")
    actions = ("mark_tokenized", "export_positions_csv",)

    def positions_count(self, obj: models.Loan) -> int:
        return models.InvestorPosition.objects.filter(loan=obj).count()

    positions_count.short_description = "Investor positions"

    def slices_sold(self, obj: models.Loan) -> float:
        qs = models.InvestorPosition.objects.filter(loan=obj)
        total = qs.aggregate(models_sum=models.models.Sum("slices_owned"))
        return float(total.get("models_sum") or 0)

    slices_sold.short_description = "Slices sold"

    def total_balance_due(self, obj: models.Loan) -> float:
        qs = models.InvestorPosition.objects.filter(loan=obj)
        total = qs.aggregate(models_sum=models.models.Sum("balance_due"))
        return float(total.get("models_sum") or 0)

    total_balance_due.short_description = "Total owed (USDC)"

    def mark_tokenized(self, request, queryset):
        updated = queryset.update(tokenized=True)
        self.message_user(request, f"Marked {updated} loan(s) as tokenized")

    mark_tokenized.short_description = "Mark selected loans as tokenized"

    def export_positions_csv(self, request, queryset):
        # export investor positions for selected loans
        positions = models.InvestorPosition.objects.filter(loan__in=queryset).select_related("investor", "loan")
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = "attachment; filename=positions_export.csv"
        writer = csv.writer(resp)
        writer.writerow(["loan_id", "investor", "wallet_address", "slices_owned", "balance_due"]) 
        for p in positions:
            writer.writerow([p.loan.loan_id, p.investor.name, p.investor.wallet_address, str(p.slices_owned), str(p.balance_due)])
        return resp

    export_positions_csv.short_description = "Export investor positions for selected loans (CSV)"


@admin.register(models.Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "wallet_address")
    search_fields = ("name", "email", "wallet_address")


@admin.register(models.InvestorPosition)
class InvestorPositionAdmin(admin.ModelAdmin):
    list_display = ("investor", "loan", "slices_owned", "ownership_percent_display", "balance_due")
    list_filter = ("loan",)
    search_fields = ("investor__name", "loan__loan_id")
    actions = ("zero_balance", "export_selected_positions",)

    def ownership_percent_display(self, obj: models.InvestorPosition) -> str:
        try:
            return f"{obj.ownership_percent:.4f}%"
        except Exception:
            return "-"

    ownership_percent_display.short_description = "Ownership %"

    def zero_balance(self, request, queryset):
        updated = queryset.update(balance_due=0)
        self.message_user(request, f"Zeroed balance_due for {updated} position(s)")

    zero_balance.short_description = "Zero balance_due for selected positions"

    def export_selected_positions(self, request, queryset):
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = "attachment; filename=selected_positions.csv"
        writer = csv.writer(resp)
        writer.writerow(["loan_id", "investor", "wallet_address", "slices_owned", "balance_due"]) 
        for p in queryset.select_related("investor", "loan"):
            writer.writerow([p.loan.loan_id, p.investor.name, p.investor.wallet_address, str(p.slices_owned), str(p.balance_due)])
        return resp

    export_selected_positions.short_description = "Export selected investor positions (CSV)"


@admin.register(models.CashflowHistory)
class CashflowHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "investor",
        "amount",
        "block_number",
        "created_at",
        "description",
    )
    list_select_related = ("loan", "investor")
    list_filter = ("created_at", "loan__status", "block_number")
    search_fields = (
        "loan__loan_id",
        "investor__wallet_address",
        "tx_hash",
        "description",
    )
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)