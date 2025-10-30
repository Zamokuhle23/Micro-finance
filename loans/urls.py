from django.urls import path
from .views import AgentDashboardView, MarkPaymentView,LoanQualificationView,LoanOfferView
from django.urls import path
from . import views

app_name = "loans"  # 

urlpatterns = [
    path('dashboard/', AgentDashboardView.as_view(), name='agent_dashboard'),
    path('mark-payment/<int:loan_id>/', MarkPaymentView.as_view(), name='mark_payment'),
    path("customers/", views.CustomerListView.as_view(), name="list_customers"),
    path("customers/new-loan/", views.CreateCustomerAndLoanView.as_view(), name="create_customer_loan"),
    path("customers/add-loan/", views.AddLoanExistingCustomerView.as_view(), name="add_loan_existing_customer"),
    path("customer/<int:customer_id>/qualification/", LoanQualificationView.as_view(), name="loan_qualification"),
    path("customer/<int:customer_id>/offer/", LoanOfferView.as_view(), name="loan_offer"),
    # loans/urls.py
    path('customer/<int:customer_id>/history/', views.CustomerHistoryView.as_view(), name='customer_history'),
    path("admin/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin/customer/<int:customer_id>/adjust_credit/", views.AdjustCustomerCreditView.as_view(), name="adjust_customer_credit"),
    path("admin/update_loan_settings/", views.UpdateLoanSettingsView.as_view(), name="update_loan_settings"),
    path("admin/customers/", views.AdminCustomerListView.as_view(), name="admin_customers"),
    path("admin/customers/<int:pk>/edit/", views.AdminCustomerEditView.as_view(), name="admin_edit_customer"),
    path('admin/agents/', views.AdminAgentsView.as_view(), name='admin_agents'),
    path('admin/agents/invite/', views.GenerateAgentInviteView.as_view(), name='generate_agent_invite'),
    path('admin/agents/edit/<int:agent_id>/', views.EditAgentView.as_view(), name='edit_agent'),



]
