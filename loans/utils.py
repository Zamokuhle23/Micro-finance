from datetime import date
from .models import Customer, Repayment

def agent_performance(agent):
    total_customers = Customer.objects.filter(agent=agent).count()
    paid_today = Repayment.objects.filter(
        recorded_by=agent.user,
        date=date.today()
    ).values('loan__customer').distinct().count()

    if total_customers == 0:
        return 0
    return round((paid_today / total_customers) * 100, 2)
