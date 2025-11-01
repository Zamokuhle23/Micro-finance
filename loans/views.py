from django.views import View
from django.views.generic import TemplateView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from datetime import date

from .models import Customer, Loan, Repayment
from .utils import agent_performance
from accounts.models import AgentProfile

from django.shortcuts import get_object_or_404, render
from django.views import View
from django.db.models import Sum
from datetime import date

class AgentDashboardView(View):
    template_name = "loans/agent_dashboard.html"
    context = {}

    def get(self, request, *args, **kwargs):
        agent_profile = get_object_or_404(AgentProfile, user=request.user)
        loans = Loan.objects.filter(customer__agent=agent_profile, status='active')

        # Loans due today
        due_loans = [loan for loan in loans if loan.is_due_today]

        # Calculate amount collected and loans collected
        amount_to_collect = sum(loan.daily_payment for loan in loans)
        amount_collected = 0
        loans_collected_count = 0

        today = date.today()
        for loan in loans:
            lactual_loan = Repayment.objects.filter(loan=loan,date=today).first()
            if lactual_loan:
               amount_collected += lactual_loan.amount_paid
               loans_collected_count += 1

        total_due_loans = len(loans)
        loan_collection_percentage = round((loans_collected_count / total_due_loans) * 100, 2) if total_due_loans else 0
        amount_collection_percentage = round((amount_collected / amount_to_collect) * 100, 2) if amount_to_collect else 0

        # Handle customer search
        name_query = request.GET.get("name", "").strip()
        phone_query = request.GET.get("phone", "").strip()
        customers = None
        searched = False

        if name_query or phone_query:
            searched = True
            customers = Customer.objects.filter(agent=agent_profile)
            if name_query:
                customers = customers.filter(name__icontains=name_query)
            if phone_query:
                customers = customers.filter(phone__icontains=phone_query)

        # Daily performance: how many due loans are already paid today
        paid_today = len(loans) - len(due_loans)
        performance = round((paid_today / len(loans)) * 100, 2) if loans else 0

        amount_in_hand = agent_profile.amount_in_hand

        self.context = {
            "agent": agent_profile,
            "amount_in_hand": amount_in_hand, 
            "loans": loans,
            "due_loans": due_loans,
            "performance": performance,
            "customers": customers,
            "searched": searched,
            "amount_to_collect": amount_to_collect,
            "amount_collected": amount_collected,
            "amount_collection_percentage": amount_collection_percentage,
            "loans_collected_count": loans_collected_count,
            "total_due_loans": total_due_loans,
            "loan_collection_percentage": loan_collection_percentage,
        }
        return render(request, self.template_name, self.context)


from decimal import Decimal

class MarkPaymentView(LoginRequiredMixin, View):
    def post(self, request, loan_id):
        loan = get_object_or_404(Loan, id=loan_id)
        agent_profile = get_object_or_404(AgentProfile, user=request.user)
        today = date.today()
        amount = request.POST.get("amount")

        # Validate payment amount
        try:
            amount = Decimal(amount) if amount else loan.daily_payment
        except:
            messages.error(request, "Invalid payment amount.")
            return redirect("loans:agent_dashboard")

        # Prevent duplicate same-amount payments in same day
        if loan.last_paid_date == today and amount == loan.daily_payment:
            messages.warning(request, "Payment already recorded for today.")
            return redirect("loans:agent_dashboard")
        
        Repayment.objects.create(
            loan=loan,
            date=today,
            amount_paid=amount,
            recorded_by=agent_profile

        )   
        # ✅ Update loan financials
        loan.total_paid += amount
        loan.last_paid_date = today
        loan.days_paid += 1
        agent_profile.amount_in_hand += amount
        agent_profile.save()

        # ✅ If total_paid >= total_due, mark loan as completed
        if loan.remaining_balance <= 0:
            loan.status = "completed"

        loan.save()

        messages.success(
            request,
            f"Payment of {amount} SZL recorded for {loan.customer.name}. Remaining balance: {loan.remaining_balance:.2f} SZL"
        )
        return redirect("loans:agent_dashboard")
    
# loans/views.py
from django.views.generic import ListView
from .models import Customer,LoanSettings
from .forms import CustomerForm, LoanForm

class CustomerListView(ListView):
    model = Customer
    template_name = "loans/customer_list.html"
    context_object_name = "customers"

class CreateCustomerAndLoanView(View):
    template_name = "loans/create_customer_loan.html"

    def get(self, request):
        customer_form = CustomerForm()
        return render(request, self.template_name, {
            'customer_form': customer_form,
        })

    def post(self, request):
        customer_form = CustomerForm(request.POST)

        if customer_form.is_valid():
            # ✅ Create customer object but don’t save yet
            customer = customer_form.save(commit=False)

            # ✅ Attach the agent to the new customer
            agent_profile = AgentProfile.objects.get(user=request.user)
            customer.agent = agent_profile

            # ✅ Save fully now
            customer.save()

            messages.success(request, f"Customer {customer.name} created successfully.")

            # ✅ Redirect directly to loan offer page for this new customer
            return redirect(f"loans:loan_qualification",customer.id)

        # ❌ Invalid form — re-render page with errors
        messages.error(request, "Please correct the errors below.")
        return render(request, self.template_name, {
            'customer_form': customer_form,
        })
    
class AddLoanExistingCustomerView(View):
    template_name = "loans/add_loan_existing.html"

    def get(self, request):
        agent_profile = get_object_or_404(AgentProfile, user=request.user)
        loan_form = LoanForm()
        # Filter only customers of this agent
        loan_form.fields['customer'].queryset = Customer.objects.filter(agent=agent_profile)
        return render(request, self.template_name, {'loan_form': loan_form})

    def post(self, request):
        agent_profile = get_object_or_404(AgentProfile, user=request.user)
        loan_form = LoanForm(request.POST)
        loan_form.fields['customer'].queryset = Customer.objects.filter(agent=agent_profile)

        if loan_form.is_valid():
            loan = loan_form.save()
            messages.success(request, f"Loan for customer '{loan.customer.name}' added successfully!")
            return redirect('loans:customer_list')
        else:
            return render(request, self.template_name, {'loan_form': loan_form})


class LoanQualificationView(View):
    template_name = "loans/loan_qualification.html"

    def get(self, request, customer_id=None):
        """
        Show loan qualification page.
        If customer_id is provided, use the existing customer.
        If no customer_id, treat as a new customer and show default ranges.
        """
        if customer_id:
            # Existing customer
            customer = get_object_or_404(Customer, id=customer_id)

            # Check if any active loan exists
            active_loan = Loan.objects.filter(customer=customer, status='active').exists()
            if active_loan:
                messages.warning(request, f"{customer.name} still has an active loan and cannot apply for another.")
                return redirect('loans:agent_dashboard')

            lower, upper = customer.loan_range()
        else:
            # New customer
            customer = None
            # Default ranges from LoanSettings (or any defaults you want)
            settings = LoanSettings.objects.first()
            lower = settings.min_loan_amount if settings else 200
            upper = settings.max_loan_amount if settings else 500

        context = {
            'customer': customer,
            'lower': lower,
            'upper': upper,
        }
        return render(request, self.template_name, context)


# loans/views.py
from decimal import Decimal

class LoanOfferView(View):
    template_name = "loans/loan_offer.html"

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, id=customer_id)

        # Default amount for new customer or passed via query param
        amount = request.GET.get("amount", 200)
        try:
            amount = float(amount)
        except ValueError:
            amount = 200

        offers = [
            {"interest": 20, "days": 20},
            {"interest": 25, "days": 25},
        ]

        # Calculate repayment details
        for offer in offers:
            total_due = amount + (amount * offer["interest"] / 100)
            offer["total_due"] = round(total_due, 2)
            offer["daily_payment"] = round(total_due / offer["days"], 2)

        return render(request, self.template_name, {
            "customer": customer,
            "amount": amount,
            "offers": offers,
        })

    def post(self, request, customer_id):
        customer = get_object_or_404(Customer, id=customer_id)
        agent_profile = AgentProfile.objects.get(user=request.user)
        interest = float(request.POST.get("interest"))
        days = int(request.POST.get("days"))
        amount = float(request.POST.get("amount"))

        total_due = amount + (amount * interest / 100)
        daily_payment = total_due / days

        # ✅ Create the loan
        Loan.objects.create(
            customer=customer,
            principal_amount=amount,
            interest_rate=interest,
            duration_days=days,
            total_due=round(total_due, 2),
            daily_payment=round(daily_payment, 2),
            status='active'
        )
        agent_profile.amount_in_hand -= Decimal(amount)
        agent_profile.save()

        messages.success(request, f"Loan created successfully for {customer.name} ({amount} SZL at {interest}% for {days} days).")
        return redirect("loans:agent_dashboard")

from calendar import monthrange
from datetime import date, timedelta
from django.utils import timezone
from .models import Customer, Loan, Repayment
import json

class CustomerHistoryView(View):
    template_name = "loans/customer_history.html"

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, id=customer_id)
        today = timezone.now().date()

        loan = Loan.objects.filter(customer=customer).order_by('-start_date').first()
        repayments = Repayment.objects.filter(loan=loan).order_by('date') if loan else []

        events = []

        if loan:
            start_date = loan.start_date
            end_date = loan.start_date + timedelta(days=loan.duration_days)
            estimated_end_date = end_date #

            for i in range((end_date - start_date).days + 1):
                day = start_date + timedelta(days=i)

                if day.weekday() >= 5:  # skip weekends
                    continue

                status = None
                color = None
                if day == loan.start_date:
                    status = "Disbursed"
                    color = "#2196F3"
                elif any(r.date == day for r in repayments):
                    status = "Paid"
                    color = "green"
                elif day < today:
                    status = "Missed"
                    color = "red"

                if status:
                    events.append({
                        "title": status,
                        "start": day.strftime("%Y-%m-%d"),
                        "color": color
                    })

        context = {
            "customer": customer,
            "loan": loan,
            "estimated_end_date": estimated_end_date, # <-- Add to context
            "events_json": json.dumps(events),  # always valid JSON string
        }
        return render(request, self.template_name, context)
    

from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import UserPassesTestMixin
from datetime import date, timedelta
from django.db.models import Sum, Count
from .models import AgentProfile, Customer, Loan, Repayment, LoanSettings,AdminTransactionRequest
from decimal import Decimal

class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff

    def handle_no_permission(self):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to access this page.")


class AdminDashboardView(AdminRequiredMixin, View):
    def get(self, request):

        # Global metrics
        total_customers = Customer.objects.count()
        total_loans = Loan.objects.count()
        active_loans = Loan.objects.filter(status="active").count()
        settings = LoanSettings.objects.first()
        pending_requests = AdminTransactionRequest.objects.filter(status='pending').select_related('agent__user')

        context = {
           
            "total_customers": total_customers,
            "total_loans": total_loans,
            "active_loans": active_loans,
            "loan_settings": settings,
            "pending_requests": pending_requests,
        }
        return render(request, "loans/admin_dashboard.html", context)


class AdjustCustomerCreditView(AdminRequiredMixin, View):
    """Admin can adjust a customer's credit score"""

    def post(self, request, customer_id):
        customer = get_object_or_404(Customer, id=customer_id)
        new_credit = request.POST.get("credit_score")
        try:
            new_credit = int(new_credit)
            customer.credit_score = new_credit
            customer.save()
            # Optional: add messages framework for success
        except:
            pass
        return redirect("loans:admin_dashboard")


class UpdateLoanSettingsView(AdminRequiredMixin, View):
    """Admin can update only provided loan setting fields."""

    def post(self, request):
        settings = LoanSettings.objects.first()
        if not settings:
            # If no settings exist yet, create one
            settings = LoanSettings.objects.create()

        # Get values from form safely
        interest = request.POST.get("interest_percent")
        duration = request.POST.get("duration_days")
        min_amount = request.POST.get("min_loan_amount")
        max_amount = request.POST.get("max_loan_amount")

        # Update only fields that have a value
        if interest:
            try:
                settings.interest_percent = Decimal(interest)
            except:
                pass

        if duration:
            try:
                settings.duration_days = int(duration)
            except:
                pass

        if min_amount:
            try:
                settings.min_loan_amount = Decimal(min_amount)
            except:
                pass

        if max_amount:
            try:
                settings.max_loan_amount = Decimal(max_amount)
            except:
                pass

        settings.save()
        return redirect("loans:admin_dashboard")

class AdminCustomerListView(AdminRequiredMixin, View):
    template_name = "loans/admin_customers.html"

    def get(self, request):
        customers = Customer.objects.select_related("agent").all()
        return render(request, self.template_name, {"customers": customers})
    
class AdminCustomerEditView(AdminRequiredMixin, View):
    template_name = "loans/admin_edit_customer.html"

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        agents = AgentProfile.objects.all()
        return render(request, self.template_name, {"customer": customer, "agents": agents})

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)

        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        location = request.POST.get("location", "").strip()
        national_id = request.POST.get("national_id", "").strip()
        credit_score = request.POST.get("credit_score", "").strip()
        agent_id = request.POST.get("agent", "").strip()

        # Only update if value is provided (not empty)
        if name:
            customer.name = name
        if phone:
            customer.phone = phone
        if location:
            customer.location = location
        if national_id:
            customer.national_id = national_id
        if credit_score:
            try:
                credit_val = int(credit_score)
                if 0 <= credit_val <= 5000:  # safe bound check
                    customer.credit_score = credit_val
            except ValueError:
                messages.warning(request, "Credit score must be a number.")
        if agent_id:
            try:
                agent = AgentProfile.objects.get(id=agent_id)
                customer.agent = agent
            except AgentProfile.DoesNotExist:
                messages.warning(request, "Invalid agent selected.")

        customer.has_active_loan = request.POST.get("has_active_loan") == "on"

        customer.save()
        messages.success(request, f"{customer.name}'s details updated successfully.")
        return redirect("loans:admin_customers")
    
import secrets
from django.urls import reverse
from accounts.models import AgentProfile,RegistrationToken

class AdminAgentsView(AdminRequiredMixin, View):
    """Admin can manage agents: view, edit, and generate invite links"""
    template_name = "loans/admin_agents.html"

    def get(self, request):
        agents = AgentProfile.objects.select_related("user").all()
        return render(request, self.template_name, {"agents": agents})

from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

@method_decorator(login_required, name='dispatch')
class GenerateAgentInviteView(View):
    """Admin/staff-only view to generate agent registration links (valid for 2 hours)"""

    def generate_link(self, request):
        token = RegistrationToken.create_token(hours_valid=2)
        registration_url = request.build_absolute_uri(f"/accounts/register/?token={token.token}")
        return registration_url, token.expires_at

    def dispatch(self, request, *args, **kwargs):
        # Check permissions for all HTTP methods
        if not (request.user.is_superuser or request.user.is_staff):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        url, expires = self.generate_link(request)
        return render(request, "accounts/admin_link.html", {"registration_url": url, "expires": expires})

    def post(self, request, *args, **kwargs):
        # same logic as GET, allows a POST button if desired
        url, expires = self.generate_link(request)
        return render(request, "accounts/admin_link.html", {"registration_url": url, "expires": expires})

class EditAgentView(View):
    """Admin can edit agent details"""

    def get(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        return render(request, "loans/edit_agent.html", {"agent": agent})

    def post(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        user = agent.user

        # Only update if field is provided and non-empty
        first_name = request.POST.get("first_name")
        if first_name:
            user.first_name = first_name

        last_name = request.POST.get("last_name")
        if last_name:
            user.last_name = last_name

        email = request.POST.get("email")
        if email:
            user.email = email

        user.save()
        messages.success(request, "Agent details updated successfully!")
        return redirect("loans:admin_agents")

class SendToAdminRequestView(View):
    def get(self, request):
        return render(request, "loans/send_to_admin.html")

    def post(self, request):
        agent = AgentProfile.objects.get(user=request.user)
        requested_amount = Decimal(request.POST.get("amount"))

        if requested_amount > agent.amount_in_hand:
            messages.error(request, "Insufficient balance")
            return redirect("loans:agent_dashboard")

        AdminTransactionRequest.objects.create(
            agent=agent,
            requested_amount=requested_amount
        )

        messages.success(request, f"Request to send {requested_amount} SZL submitted for admin approval.")
        return redirect("loans:agent_dashboard")
    

class AdminApproveTransactionView(UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff

    def post(self, request, request_id):
        transaction_request = get_object_or_404(AdminTransactionRequest, id=request_id)
        action = request.POST.get('action')
        actual_amount = request.POST.get('actual_amount')
        rejection_note = request.POST.get('rejection_note')

        if action == 'approve':
            amount = transaction_request.requested_amount
            if actual_amount:
                try:
                    amount = float(actual_amount)
                except ValueError:
                    messages.error(request, "Invalid amount entered.")
                    return redirect('loans:admin_dashboard')

            # Approve and subtract
            transaction_request.status = 'approved'
            transaction_request.actual_received_amount = amount
            transaction_request.agent.amount_in_hand -= amount
            transaction_request.agent.save()
            transaction_request.save()
            messages.success(request, f"Approved {transaction_request.agent.user.username}'s request of {amount}.")

        elif action == 'reject':
            transaction_request.status = 'rejected'
            transaction_request.rejection_note = rejection_note or "No reason provided."
            transaction_request.save()
            messages.warning(request, f"Rejected {transaction_request.agent.user.username}'s request.")

        return redirect('loans:admin_dashboard')
    


def admin_required(user):
    return user.is_staff or user.is_superuser

@method_decorator([login_required, user_passes_test(admin_required)], name='dispatch')
class AgentDetailView(View):
    def get(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        return render(request, "loans/agent_detail.html", {"agent": agent})


@method_decorator([login_required, user_passes_test(admin_required)], name='dispatch')
class AdminGiveAgentMoneyView(View):
    def post(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        try:
            amount = Decimal(request.POST.get("amount"))
            if amount <= 0:
                messages.error(request, "Amount must be greater than zero.")
                return redirect("loans:agent_detail", agent_id=agent.id)
        except:
            messages.error(request, "Invalid amount entered.")
            return redirect("loans:agent_detail", agent_id=agent.id)

        # Add money to agent's amount_in_hand
        agent.amount_in_hand += amount
        agent.save()

        messages.success(request, f"{amount} SZL successfully given to {agent.user.get_full_name()}.")
        return redirect("loans:agent_detail", agent_id=agent.id)