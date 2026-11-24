import random
from datetime import timedelta, date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from cases.models import RecoveryCase, Activity, Document, Payment, Profile, ThirdPartyEvent, STATUSES, DEFAULT_DOCS

NAMES = ["Rahul Sharma", "Sneha Patil", "Vikram Joshi", "Anita Deshmukh", "Karan Mehta", "Pooja Nair", "Rohit Kulkarni",
         "Meena Iyer", "Sanjay Gupta", "Divya Rao", "Arjun Singh", "Neha Kapoor", "Imran Shaikh", "Lata More", "Suresh Pawar"]
THIRD = ["Bharat General Insurance", "Sunrise Motors Pvt Ltd", "Metro Assurance Co.", "Kaveri Insurance", "Delta Logistics"]


class Command(BaseCommand):
    help = "Load demo users and sample cases"

    def handle(self, *a, **kw):
        U = get_user_model()

        def person(username, password, role, name):
            u, _ = U.objects.get_or_create(username=username, defaults={"first_name": name})
            u.set_password(password)
            u.is_staff = u.is_superuser = role == "manager"
            u.save()
            Profile.objects.update_or_create(user=u, defaults={"role": role})
            return u

        person("manager", "manager123", "manager", "Meera Kulkarni")
        emps = [person("priya", "pass1234", "employee", "Priya Desai"), person("amit", "pass1234", "employee", "Amit Verma")]
        clients = [person("rahul", "pass1234", "client", "Rahul Sharma"), person("sneha", "pass1234", "client", "Sneha Patil"),
                   person("vikram", "pass1234", "client", "Vikram Joshi")]
        now = timezone.now()
        random.seed(7)
        for i, name in enumerate(NAMES):
            if RecoveryCase.objects.filter(claim_id=f"CLM-{1001 + i}").exists(): continue
            client = clients[i % 5] if i % 5 < 3 else None
            paid = Decimal(random.choice([75000, 120000, 200000, 350000]))
            stale = i % 5 == 2
            status = random.choice(STATUSES[:5]) if i < 12 else random.choice(STATUSES[5:])
            if stale: status = "Awaiting Response"
            age = random.randint(20, 30) if stale else random.randint(1, 9)
            third = random.choice(THIRD)
            c = RecoveryCase.objects.create(claim_id=f"CLM-{1001 + i}", policyholder=client.first_name if client else name, third_party=third,
                incident_details="Two-vehicle collision; third party found at fault per police report.", amount_paid=paid, status=status,
                assigned_to=emps[i % 2], client=client,
                next_followup_date=date.today() + timedelta(days=-(age // 2) if stale else random.randint(-1, 8)))
            for n in DEFAULT_DOCS:
                Document.objects.create(case=c, name=n, status="pending" if (n == "Payment proof" and i % 2 == 0) else "received")
            first = Activity.objects.create(case=c, type="system", description=f"Recovery case created from claim {c.claim_id}.")
            second = Activity.objects.create(case=c, type="third_party", description=f"{third}: Recovery request sent", created_by=emps[i % 2])
            Activity.objects.filter(pk=first.pk).update(created_at=now - timedelta(days=age + 5))
            Activity.objects.filter(pk=second.pk).update(created_at=now - timedelta(days=age))
            ThirdPartyEvent.objects.create(case=c, event_type="request_sent", party=third, event_date=date.today() - timedelta(days=age),
                                           reference_no=f"RQ-{2000 + i}", created_by=emps[i % 2])
            if i % 3 == 0 and not stale:
                ThirdPartyEvent.objects.create(case=c, event_type="acknowledged", party=third, event_date=date.today() - timedelta(days=age - 2), created_by=emps[i % 2])
            if i % 4 == 1:
                ThirdPartyEvent.objects.create(case=c, event_type="offer", party=third, amount=paid * Decimal("0.7"),
                                               note="Offered 70% citing shared liability", event_date=date.today() - timedelta(days=max(age - 3, 0)), created_by=emps[i % 2])
            if status.startswith("Recovered"):
                Payment.objects.create(case=c, amount=paid * Decimal("0.6"), date=date.today() - timedelta(days=age), note="Part payment", paid_by=third)
        self.stdout.write(self.style.SUCCESS("Seeded. Logins: manager/manager123, priya/pass1234, amit/pass1234, rahul/pass1234 (client)"))
