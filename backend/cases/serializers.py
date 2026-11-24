from rest_framework import serializers
from .models import RecoveryCase, Activity, Document, Payment, ThirdPartyEvent, AgentRun, AgentFinding
from .services import case_alert

CLIENT_KINDS = ("status", "third_party", "document")
money = lambda: serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class ActivitySerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default="system")

    class Meta:
        model = Activity
        fields = ["id", "type", "description", "created_by_name", "created_at"]
        read_only_fields = ["created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    text_preview = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True, default=None)

    class Meta:
        model = Document
        fields = ["id", "case", "name", "is_required", "status", "file", "uploaded_at", "uploaded_by_name", "ai_summary",
                  "extracted_details", "check_result", "ai_source", "processed_at", "text_preview"]
        read_only_fields = fields

    def get_text_preview(self, d):
        return d.extracted_text[:1500]


class ClientDocumentSerializer(serializers.ModelSerializer):
    issues = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "name", "is_required", "status", "file", "uploaded_at", "issues"]

    def get_issues(self, d):
        return (d.check_result or {}).get("missing", [])


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "case", "amount", "date", "note", "paid_by"]
        extra_kwargs = {"case": {"read_only": True}}

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return v


class ThirdPartyEventSerializer(serializers.ModelSerializer):
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = ThirdPartyEvent
        fields = ["id", "event_type", "event_label", "party", "reference_no", "amount", "note", "event_date", "created_by_name"]


class CaseSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.username", read_only=True, default=None)
    client_name = serializers.CharField(source="client.username", read_only=True, default=None)
    amount_recovered, remaining_amount = money(), money()
    alert = serializers.SerializerMethodField()

    class Meta:
        model = RecoveryCase
        fields = ["id", "recovery_id", "claim_id", "policyholder", "incident_details", "third_party", "amount_paid",
                  "expected_recovery", "status", "assigned_to", "assigned_to_name", "client", "client_name",
                  "next_followup_date", "created_at", "amount_recovered", "remaining_amount", "alert"]
        read_only_fields = ["recovery_id", "created_at"]
        extra_kwargs = {"expected_recovery": {"required": False}}

    def get_alert(self, obj):
        a = case_alert(obj)
        return {k: a[k] for k in ("level", "reasons", "inactive_days")}


class CaseDetailSerializer(CaseSerializer):
    activities = ActivitySerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    third_party_events = ThirdPartyEventSerializer(source="tp_events", many=True, read_only=True)

    class Meta(CaseSerializer.Meta):
        fields = CaseSerializer.Meta.fields + ["activities", "documents", "payments", "third_party_events"]


class ClientCaseSerializer(serializers.ModelSerializer):
    amount_recovered, remaining_amount = money(), money()
    documents = ClientDocumentSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    third_party_events = ThirdPartyEventSerializer(source="tp_events", many=True, read_only=True)
    timeline = serializers.SerializerMethodField()
    missing_documents = serializers.SerializerMethodField()

    class Meta:
        model = RecoveryCase
        fields = ["id", "recovery_id", "claim_id", "policyholder", "incident_details", "third_party", "amount_paid",
                  "expected_recovery", "status", "created_at", "amount_recovered", "remaining_amount", "documents",
                  "payments", "third_party_events", "timeline", "missing_documents"]

    def get_timeline(self, c):
        return ActivitySerializer([a for a in c.activities.all() if a.type in CLIENT_KINDS], many=True).data

    def get_missing_documents(self, c):
        return [d.name for d in c.documents.all() if d.is_required and d.status == "pending"]


class AgentFindingSerializer(serializers.ModelSerializer):
    recovery_id = serializers.CharField(source="case.recovery_id", read_only=True)
    policyholder = serializers.CharField(source="case.policyholder", read_only=True)
    case_status = serializers.CharField(source="case.status", read_only=True)

    class Meta:
        model = AgentFinding
        fields = ["id", "case", "recovery_id", "policyholder", "case_status", "priority", "score", "level",
                  "reasons", "reason", "suggested_action", "source", "status", "employee_note", "responded_at"]


class AgentRunSerializer(serializers.ModelSerializer):
    findings = AgentFindingSerializer(many=True, read_only=True)

    class Meta:
        model = AgentRun
        fields = ["id", "instruction", "summary", "tool_trace", "source", "created_at", "findings"]
