from django.urls import path
from app import views

app_name = "rwa"
# -------------------------
# SPV / ADMIN
# -------------------------
spv_patterns = [
    path("spv/dashboard/", views.spv_dashboard, name="spv_dashboard"),
    path("spv/loans/add/", views.spv_loan_add, name="spv_add_loan"),
    path("spv/loans/<str:loan_id>/edit/", views.spv_loan_edit, name="spv_edit_loan"),
    path("spv/loans/<str:loan_id>/delete/", views.spv_loan_delete, name="spv_loan_delete"),
    path("spv/loans/", views.spv_loans_list, name="spv_loans"),
    path("spv/loan/<str:loan_id>/", views.spv_loan_detail, name="spv_loan_detail"),
    path("spv/investors/", views.investor_list, name="investor_list"),
    path("spv/investors/view/<str:investor_id>/", views.investor_view, name="investor_view"),
    path("spv/investors/add/", views.add_investor, name="add_investor"),

    path("spv/loan/<str:loan_id>/review_tokenization/", views.review_tokenization, name="review_tokenization"),
    path("spv/loan/<str:loan_id>/tokenize/", views.spv_tokenize_loan, name="confirm_tokenize_loan"),
    path("spv/loan/<str:loan_id>/distribute/", views.spv_distribute_payment, name="distribute_payment"),
    path("spv/loan/<str:loan_id>/positions/create", views.spv_create_position, name="create_investor_position"),
    path('spv/<int:investor_id>/positions/', views.spv_investor_positions, name='investor_positions'),
]

urlpatterns = spv_patterns