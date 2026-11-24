"""Rule-based detection for follow-up reminders (feature 3) and delayed cases (feature 5).
These are plain database checks - no LLM needed - so they are fast and always accurate."""
from datetime import date
from django.conf import settings
from django.utils import timezone
from .models import RecoveryCase
from .access import role_of

OPEN_EXCLUDED = ["Closed", "Recovered / Partially Recovered"]


def case_alert(case):
    now, today = timezone.now(), date.today()
    inactive = (now - case.last_activity_at).days
    reasons, score = [], 0
    overdue = bool(case.next_followup_date and case.next_followup_date < today)
    due_soon = bool(case.next_followup_date and 0 <= (case.next_followup_date - today).days <= 2)
    missing = [d.name for d in case.documents.all() if d.is_required and d.status == "pending"]
    if overdue:
        days = (today - case.next_followup_date).days
        reasons.append(f"Follow-up overdue by {days} day(s)"); score += 50 + days
    elif due_soon:
        reasons.append(f"Follow-up due on {case.next_followup_date:%d %b}"); score += 20
    if inactive >= settings.DELAY_THRESHOLD_DAYS:
        reasons.append(f"No activity for {inactive} days"); score += 40 + inactive
    if missing:
        reasons.append("Missing documents: " + ", ".join(missing)); score += 10 * len(missing)
    if case.status == "Awaiting Response" and inactive >= 7:
        reasons.append("Awaiting a response for over a week"); score += 15
    return {"inactive_days": inactive, "overdue": overdue, "missing_docs": missing,
            "reasons": reasons, "score": score,
            "level": "Overdue" if overdue else ("Needs Attention" if score >= 40 else "Upcoming" if reasons else "OK")}


def get_alerts(user=None):
    qs = RecoveryCase.objects.exclude(status__in=OPEN_EXCLUDED).select_related("assigned_to") \
        .prefetch_related("documents", "activities")
    if user:
        role = role_of(user)
        if role == "client":
            return []
        if role == "employee":
            qs = qs.filter(assigned_to=user)
    out = []
    for c in qs:
        a = case_alert(c)
        if a["reasons"]:
            out.append({"id": c.id, "recovery_id": c.recovery_id, "policyholder": c.policyholder,
                        "status": c.status, "assigned_to": c.assigned_to.username if c.assigned_to else None,
                        "remaining_amount": c.remaining_amount, **a})
    return sorted(out, key=lambda x: -x["score"])
