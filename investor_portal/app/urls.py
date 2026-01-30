# app/urls.py
from django.urls import path
from . import views

app_name = "rwa"

# -------------------------
# PUBLIC (READ-ONLY)
# -------------------------
public_patterns = [
    path("", views.public_loans_list, name="loans_list"),
    path("loan/<str:loan_id>/", views.public_loan_detail, name="loan_detail"),
    path("metadata/loan/<str:loan_id>/", views.loan_metadata, name="loan_metadata"),
]

# -------------------------
# INVESTOR
# -------------------------
investor_patterns = [
    # path("investor/buy/<str:loan_id>/", views.buy_slices, name="buy_slices"),
    path("investor/view/", views.investor_holdings, name="investor_holdings"),
    path("investor/<str:wallet>/", views.investor_positions, name="investor_dashboard"),
]



urlpatterns = public_patterns + investor_patterns 
# This combines all the URL patterns into a single list 