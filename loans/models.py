from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta
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
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    principal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    total_due = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    daily_payment = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    duration_days = models.IntegerField(default=20)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    last_paid_date = models.DateField(null=True, blank=True)  # NEW FIELD
    days_paid = models.IntegerField(default=0)

    # # NEW FIELDS
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # remaining_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # If start_date is None (object not yet saved), set it to today
        if not self.start_date:
            self.start_date = date.today()

        if not self.total_due:
            self.total_due = self.principal_amount + (self.principal_amount * self.interest_rate / 100)
        if not self.daily_payment:
            self.daily_payment = self.total_due / self.duration_days
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=self.duration_days)

        super().save(*args, **kwargs)

    @property
    def days_elapsed(self):
        return (date.today() - self.start_date).days

    # @property
    # def days_paid(self):
    #     return self.repayment_set.count()
    
    @property
    def is_due_today(self):
        """
        Loan is due today if it's active and last payment date is NOT today.
        """
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

    def __str__(self):
        return f"{self.customer.name} - {self.principal_amount} SZL"
    
    @staticmethod
    def _next_business_day(d: date) -> date:
        """Return d if it's a business day, otherwise advance to next Mon-Fri."""
        nd = d
        while nd.weekday() >= 5:  # 5=Sat, 6=Sun
            nd += timedelta(days=1)
        return nd

    @property
    def next_payment_date(self):
        """
        Returns a human-friendly label for the next payment day:
        - 'Today'
        - 'Tomorrow'
        - 'On Monday' (or the next weekday)
        - None if loan fully paid
        """
        if self.is_fully_paid:
            return None

        today = date.today()

        # If already paid today → next business day after today
        if self.last_paid_date == today:
            next_day = self._next_business_day(today + timedelta(days=1))
        # If missed payments → due today (or next business day if weekend)
        elif getattr(self, "days_missed", 0) > 0:
            next_day = self._next_business_day(today)
        # If no payments yet → start today (or next business day)
        elif not self.last_paid_date:
            next_day = self._next_business_day(today)
        else:
            # Otherwise, general case: next business day after last payment
            next_day = self._next_business_day(self.last_paid_date + timedelta(days=1))

        # ---- Friendly text formatting ----
        if next_day == today:
            return "Today"
        elif next_day == today + timedelta(days=1):
            return "Tomorrow"
        else:
            # Example: if next_day is Monday, return "On Monday"
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
