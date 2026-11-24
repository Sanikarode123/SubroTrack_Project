from django.conf import settings
from django.db import models
from django.db.models import Sum

STATUSES = ["New Case", "Under Investigation", "Recovery Initiated", "Awaiting Response",
            "Negotiation / Follow-up", "Recovered / Partially Recovered", "Closed"]
STATUS_CHOICES = [(s, s) for s in STATUSES]
DEFAULT_DOCS = ["Accident report", "Repair bill", "Payment proof", "Photographs"]
User = settings.AUTH_USER_MODEL


class RecoveryCase(models.Model):
    recovery_id = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    claim_id = models.CharField(max_length=40, unique=True)  # unique => prevents duplicate cases
    policyholder = models.CharField(max_length=120)
    incident_details = models.TextField(blank=True)
    third_party = models.CharField(max_length=160, blank=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    expected_recovery = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="New Case")
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    client = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="client_cases")
    next_followup_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *a, **kw):
        if self.expected_recovery is None:
            self.expected_recovery = self.amount_paid
        super().save(*a, **kw)
        if not self.recovery_id:
            self.recovery_id = f"SUB-{1000 + self.pk}"
            super().save(update_fields=["recovery_id"])

    @property
    def amount_recovered(self):
        return self.payments.aggregate(t=Sum("amount"))["t"] or 0

    @property
    def remaining_amount(self):
        return self.expected_recovery - self.amount_recovered

    @property
    def last_activity_at(self):
        last = self.activities.order_by("-created_at").first()
        return last.created_at if last else self.created_at

    def __str__(self):
        return self.recovery_id or self.claim_id


class Activity(models.Model):
    TYPES = [("status", "Status change"), ("followup", "Follow-up"), ("note", "Note"), ("system", "System"),
             ("document", "Document"), ("third_party", "Third party")]
    case = models.ForeignKey(RecoveryCase, on_delete=models.CASCADE, related_name="activities")
    type = models.CharField(max_length=12, choices=TYPES, default="note")
    description = models.TextField()
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Document(models.Model):
    case = models.ForeignKey(RecoveryCase, on_delete=models.CASCADE, related_name="documents")
    name = models.CharField(max_length=120)
    is_required = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=[("pending", "Pending"), ("received", "Received")], default="pending")
    file = models.FileField(upload_to="docs/%Y/%m/", null=True, blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # AI document processing
    extracted_text = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    extracted_details = models.JSONField(default=dict, blank=True)
    check_result = models.JSONField(default=dict, blank=True)
    ai_source = models.CharField(max_length=10, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)


class Payment(models.Model):
    case = models.ForeignKey(RecoveryCase, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    paid_by = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-date"]


class AgentRun(models.Model):
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    instruction = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    tool_trace = models.JSONField(default=list)
    source = models.CharField(max_length=10, default="rules")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AgentFinding(models.Model):
    STATUS = [(x, x) for x in ("open", "accepted", "done", "snoozed", "dismissed", "superseded")]
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="findings")
    case = models.ForeignKey(RecoveryCase, on_delete=models.CASCADE, related_name="agent_findings")
    priority = models.CharField(max_length=8)
    score = models.IntegerField(default=0)
    level = models.CharField(max_length=20, blank=True)
    reasons = models.JSONField(default=list)
    reason = models.TextField()
    suggested_action = models.TextField()
    source = models.CharField(max_length=10, default="rules")
    status = models.CharField(max_length=12, choices=STATUS, default="open")
    employee_note = models.TextField(blank=True)
    responded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-score"]


class Profile(models.Model):
    ROLES = [("manager", "Manager"), ("employee", "Employee"), ("client", "Client")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLES, default="employee")

    def __str__(self):
        return f"{self.user} ({self.role})"


class ThirdPartyEvent(models.Model):
    TYPES = [("request_sent", "Recovery request sent"), ("acknowledged", "Acknowledged by insurer"),
             ("query", "Query / more information requested"), ("info_sent", "Information sent to insurer"),
             ("offer", "Settlement offer received"), ("partial_payment", "Part payment promised"),
             ("rejected", "Claim rejected / disputed"), ("settled", "Settlement agreed")]
    case = models.ForeignKey(RecoveryCase, on_delete=models.CASCADE, related_name="tp_events")
    event_type = models.CharField(max_length=20, choices=TYPES)
    party = models.CharField(max_length=160, blank=True)
    reference_no = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)
    event_date = models.DateField()
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_date", "-id"]
