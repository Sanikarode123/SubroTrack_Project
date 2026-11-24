import random
from datetime import timedelta, date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from cases.models import RecoveryCase, Activity, Payment, Document, DEFAULT_DOCS

NAMES = ["Anil Rane", "Kavita Shah", "Dinesh Patel", "Smita Joshi", "Farhan Ali", "Ritu Bansal", "Gopal Naik", "Usha Menon", "Tarun Das", "Leena Kapoor"]
# how slow each insurer tends to be (used only to create believable demo history)
THIRD = {"Bharat General Insurance": 1.0, "Sunrise Motors Pvt Ltd": 1.8, "Metro Assurance Co.": 1.2, "Kaveri Insurance": 2.2, "Delta Logistics": 1.5}


class Command(BaseCommand):
    help = "Create about 150 historical cases over the last 12 months so the analytics page has data"

    def handle(self, *a, **kw):
        emps = list(get_user_model().objects.filter(profile__role="employee"))
        if not emps:
            raise CommandError("Run `python manage.py seed` first.")
        random.seed(11)
        today, now, made = date.today(), timezone.now(), 0
        for n in range(150):
            cid = f"HIS-{3000 + n}"
            if RecoveryCase.objects.filter(claim_id=cid).exists(): continue
            born = now - timedelta(days=random.randint(5, 360))
            paid = Decimal(random.choice([45000, 80000, 120000, 180000, 240000, 320000, 450000]))
            third = random.choice(list(THIRD))
            slow = THIRD[third] * (1.4 if paid >= 250000 else 1.0)
            c = RecoveryCase.objects.create(claim_id=cid, policyholder=random.choice(NAMES), third_party=third, amount_paid=paid,
                                            assigned_to=random.choice(emps), status="New Case")
            for d in DEFAULT_DOCS: Document.objects.create(case=c, name=d, status="received")
            # activity history with insurer-dependent gaps
            t, last = born, born
            Activity.objects.create(case=c, type="system", description="Case created.")
            Activity.objects.filter(case=c).update(created_at=born)
            for _ in range(random.randint(2, 6)):
                t += timedelta(days=max(1, int(random.randint(2, 10) * slow)))
                if t > now: break
                a = Activity.objects.create(case=c, type="followup", description="Follow-up with third party.")
                Activity.objects.filter(pk=a.pk).update(created_at=t); last = t
            # outcome: older cases are more likely to be resolved
            age = (now - born).days
            resolved = random.random() < min(0.85, age / 150)
            total = Decimal(0)
            if resolved:
                pay_day = born + timedelta(days=int(random.randint(15, 60) * slow))
                for part in range(random.choice([1, 1, 2, 3])):
                    pd = (pay_day + timedelta(days=part * random.randint(10, 25))).date()
                    if pd > today: break
                    amt = (paid * Decimal(random.choice([0.35, 0.5, 0.65, 1.0]) if part == 0 else random.choice([0.2, 0.3]))).quantize(Decimal("1"))
                    amt = min(amt, paid - total)
                    if amt <= 0: break
                    Payment.objects.create(case=c, amount=amt, date=pd, note="Recovery payment", paid_by=third); total += amt
            if total >= paid: c.status = "Closed"
            elif total > 0: c.status = "Recovered / Partially Recovered"
            else: c.status = random.choice(["Under Investigation", "Recovery Initiated", "Awaiting Response", "Negotiation / Follow-up"])
            c.save(update_fields=["status"])
            RecoveryCase.objects.filter(pk=c.pk).update(created_at=born)
            made += 1
        self.stdout.write(self.style.SUCCESS(f"Created {made} historical cases."))
