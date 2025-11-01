from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta
from decimal import Decimal
from accounts.models import AgentProfile


class Customer(models.Model):
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    location = models.CharField(max_length=100, blank=True, null=True)  # <-- new field
    national_id = models.CharField(max_length=20, unique=True)
    created_at = models.DateField(auto_now_add=True)

    # Credit system fields
    credit_score = models.IntegerField(default=500)  # determines upper limit
    has_active_loan = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def loan_range(self):
        """Return current qualification range"""
        lower = 200
        upper = self.credit_score
        return lower, upper

    def update_credit_score(self, loan):
        """Update score based on performance of the last loan"""
        if loan.status != "completed":
            return

        days_early = (loan.end_date - loan.last_paid_date).days if loan.last_paid_date else 0

        if loan.days_missed == 0 and days_early >= 3:
            # Paid early
            self.credit_score = min(self.credit_score + 250, 2000)
        elif loan.days_missed == 0:
            # Paid on time
            self.credit_score = min(self.credit_score + 200, 2000)
        else:
            # Paid late or missed
            self.credit_score = max(self.credit_score - 100, 200)

        self.save()


    

class Loan(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE)
    principal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    total_due = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    daily_payment = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    duration_days = models.IntegerField(default=20)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    last_paid_date = models.DateField(null=True, blank=True)
    days_paid = models.IntegerField(default=0)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        from loans.models import PublicHoliday  # avoid circular import

        # 1️⃣ Calculate financial values if missing
        if not self.total_due:
            self.total_due = self.principal_amount + (
                self.principal_amount * self.interest_rate / Decimal(100)
            )
        if not self.daily_payment:
            self.daily_payment = self.total_due / Decimal(self.duration_days)

        # 2️⃣ Determine valid start date (not today, not weekend, not public holiday)
        if not self.start_date:
            proposed_date = date.today() + timedelta(days=1)  # start from tomorrow
            holidays = set(PublicHoliday.objects.values_list("holiday_date", flat=True))
            while proposed_date.weekday() >= 5 or proposed_date in holidays:
                proposed_date += timedelta(days=1)
            self.start_date = proposed_date

        # 3️⃣ Set end date based on start date
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.duration_days)

        super().save(*args, **kwargs)

    # ---------------- Utility methods ----------------
    @property
    def days_elapsed(self):
        return (date.today() - self.start_date).days

    @property
    def is_due_today(self):
        if self.status != "active":
            return False
        today = date.today()
        return self.last_paid_date != today

    @property
    def days_missed(self):
        missed = self.days_elapsed - self.days_paid
        return max(missed, 0)

    @property
    def is_fully_paid(self):
        return self.remaining_balance <= 0

    @property
    def remaining_balance(self):
        return max(self.total_due - self.total_paid, 0)

    @property
    def payment_status_color(self):
        if self.days_missed == 0:
            return "green"
        elif self.days_missed <= 3:
            return "yellow"
        else:
            return "red"

    @staticmethod
    def _next_business_day(d: date) -> date:
        """Return next valid business day (skip weekends + public holidays)."""
        from loans.models import PublicHoliday
        holidays = set(PublicHoliday.objects.values_list("holiday_date", flat=True))
        nd = d
        while nd.weekday() >= 5 or nd in holidays:  # 5=Sat, 6=Sun
            nd += timedelta(days=1)
        return nd

    @property
    def next_payment_date(self):
        if self.is_fully_paid:
            return None

        today = date.today()

        if self.last_paid_date == today:
            next_day = self._next_business_day(today + timedelta(days=1))
        elif getattr(self, "days_missed", 0) > 0:
            next_day = self._next_business_day(today)
        elif not self.last_paid_date:
            next_day = self._next_business_day(today)
        else:
            next_day = self._next_business_day(self.last_paid_date + timedelta(days=1))

        if next_day == today:
            return "Today"
        elif next_day == today + timedelta(days=1):
            return "Tomorrow"
        else:
            return f"On {next_day.strftime('%A')}"

    def __str__(self):
        return f"{self.customer.name} - {self.principal_amount} SZL"
    

class Repayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    date = models.DateField(default=date.today)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_by = models.ForeignKey(AgentProfile, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('loan', 'date')  # Only one payment per day per loan

    def __str__(self):
        return f"{self.loan.customer.name} - {self.amount_paid} on {self.date}"

# loans/models.py
class LoanSettings(models.Model):
    interest_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    duration_days = models.PositiveIntegerField(default=20)
    min_loan_amount = models.DecimalField(max_digits=10, decimal_places=2, default=200)
    max_loan_amount = models.DecimalField(max_digits=10, decimal_places=2, default=500)




class AdminTransactionRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE)
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    actual_received_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    rejection_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def approve(self, actual_amount=None):
        """Admin approves and updates agent balance."""
        self.status = 'approved'
        self.actual_received_amount = actual_amount or self.requested_amount
        self.agent.amount_in_hand -= self.actual_received_amount
        self.agent.save()
        self.save()


    
class PublicHoliday(models.Model):
    name = models.CharField(max_length=100)
    holiday_date = models.DateField(unique=True)  # renamed

    def __str__(self):
        return f"{self.name} ({self.holiday_date})"

    @staticmethod
    def is_holiday(check_date: date) -> bool:
        return PublicHoliday.objects.filter(holiday_date=check_date).exists()
