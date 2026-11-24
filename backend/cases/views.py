import csv, io, re
from datetime import date
from decimal import Decimal, InvalidOperation
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import ai, agent, doc_ai
from .access import role_of, visible_cases, need
from .models import (RecoveryCase, Activity, Document, Payment, ThirdPartyEvent, Profile, AgentRun, AgentFinding,
                     STATUSES, DEFAULT_DOCS)
from .serializers import (CaseSerializer, CaseDetailSerializer, ClientCaseSerializer, ClientDocumentSerializer, ActivitySerializer, DocumentSerializer,
                          PaymentSerializer, ThirdPartyEventSerializer, AgentRunSerializer, AgentFindingSerializer)
from .services import get_alerts, OPEN_EXCLUDED

User = get_user_model()
STAFF = ("manager", "employee")
FLAG_COLS = ["subrogation_potential", "subrogation", "subrogation_identified", "subrogation_flag", "subrogation_eligible", "recovery_eligible"]
YES = {"yes", "y", "true", "1", "identified", "eligible", "subrogation", "subrogated"}
# a third-party response moves the case forward in the workflow (never backwards)
STAGE_FOR_EVENT = {"request_sent": "Awaiting Response", "acknowledged": "Awaiting Response", "query": "Negotiation / Follow-up",
                   "offer": "Negotiation / Follow-up", "partial_payment": "Negotiation / Follow-up", "rejected": "Negotiation / Follow-up"}
norm = lambda k: re.sub(r"[^a-z0-9]+", "_", str(k or "").strip().lower()).strip("_")


def pick(row, *keys):
    for k in keys:
        if k and str(row.get(k, "")).strip():
            return str(row[k]).strip()
    return ""


def read_rows(f):
    if f.name.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        rows = list(load_workbook(f, read_only=True, data_only=True).active.iter_rows(values_only=True))
        head = [norm(h) for h in rows[0]]
        return [dict(zip(head, ["" if v is None else str(v) for v in r])) for r in rows[1:] if any(r)]
    reader = csv.DictReader(io.StringIO(f.read().decode("utf-8-sig")))
    return [{norm(k): (v or "") for k, v in r.items()} for r in reader]


def log(case, user, type_, text):
    Activity.objects.create(case=case, type=type_, description=text, created_by=user)


def new_case_setup(case, user):
    Document.objects.bulk_create([Document(case=case, name=n) for n in DEFAULT_DOCS])
    log(case, user, "system", f"Recovery case created from claim {case.claim_id}.")


def money(v):
    try:
        return Decimal(str(v))
    except InvalidOperation:
        raise ValidationError("Enter a valid amount.")


# ---------------- auth / users ----------------
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
    if not user:
        return Response({"detail": "Wrong username or password."}, status=400)
    role, want = role_of(user), request.data.get("role")
    if want and want != role:
        return Response({"detail": f"This is a {role} account. Use the {role.capitalize()} tab to sign in."}, status=400)
    return Response({"token": Token.objects.get_or_create(user=user)[0].key, "role": role})


@api_view(["GET"])
def me(request):
    u = request.user
    return Response({"id": u.id, "username": u.username, "name": u.get_full_name() or u.username, "role": role_of(u)})


@api_view(["GET", "POST"])
def users(request):
    need(request.user, "manager")
    if request.method == "POST":
        d = request.data
        username, password, role = (d.get("username") or "").strip(), d.get("password") or "", d.get("role")
        if role not in ("employee", "client"): raise ValidationError("Role must be employee or client.")
        if not username or len(password) < 6: raise ValidationError("Username and a password of at least 6 characters are required.")
        if User.objects.filter(username=username).exists(): raise ValidationError("That username is already taken.")
        u = User.objects.create_user(username, password=password, first_name=(d.get("name") or "").strip())
        Profile.objects.create(user=u, role=role)
    return Response([{"id": u.id, "username": u.username, "name": u.first_name, "role": role_of(u)} for u in User.objects.order_by("username")])


# ---------------- cases ----------------
class CaseViewSet(viewsets.ModelViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = visible_cases(self.request.user).select_related("assigned_to", "client") \
            .prefetch_related("documents", "activities", "payments", "tp_events")
        p = self.request.query_params
        if p.get("status"): qs = qs.filter(status=p["status"])
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(Q(recovery_id__icontains=q) | Q(claim_id__icontains=q) | Q(policyholder__icontains=q))
        return qs

    def get_serializer_class(self):
        if role_of(self.request.user) == "client": return ClientCaseSerializer
        return CaseDetailSerializer if self.action == "retrieve" else CaseSerializer

    def create(self, request, *a, **kw):
        need(request.user, "manager")
        return super().create(request, *a, **kw)

    def destroy(self, request, *a, **kw):
        need(request.user, "manager")
        return super().destroy(request, *a, **kw)

    def update(self, request, *a, **kw):
        role = role_of(request.user)
        if role == "client": raise PermissionDenied("Clients cannot edit cases.")
        if role == "employee":
            if set(request.data.keys()) - {"status", "next_followup_date"}:
                raise PermissionDenied("Employees can only update the status and the follow-up date.")
            if request.data.get("status") == "Closed":
                raise PermissionDenied("Only a manager can close a case.")
        return super().update(request, *a, **kw)

    def perform_create(self, ser):
        new_case_setup(ser.save(), self.request.user)

    def perform_update(self, ser):
        old = ser.instance.status
        case = ser.save()
        if case.status != old:
            log(case, self.request.user, "status", f"Status changed: {old} -> {case.status}")

    @action(detail=True, methods=["post"])
    def activities(self, request, pk=None):
        need(request.user, *STAFF)
        case, d = self.get_object(), request.data
        a = Activity.objects.create(case=case, type=d.get("type", "note"), description=d.get("description", ""), created_by=request.user)
        if d.get("next_followup_date"):
            case.next_followup_date = d["next_followup_date"]
            case.save(update_fields=["next_followup_date"])
        return Response(ActivitySerializer(a).data, status=201)

    @action(detail=True, methods=["post"])
    def documents(self, request, pk=None):
        case, f = self.get_object(), request.FILES.get("file")
        role = role_of(request.user)
        if role == "client" and not f: raise ValidationError("Choose a file to upload.")
        name = request.data.get("name") or (f.name if f else "")
        if not name: raise ValidationError("Document name or file required.")
        doc = Document.objects.filter(case=case, name__iexact=name).first() or Document(case=case, name=name, is_required=False)
        if f:
            doc.file, doc.status, doc.uploaded_at, doc.uploaded_by = f, "received", timezone.now(), request.user
        doc.save()
        who = "Client" if role == "client" else request.user.username
        log(case, request.user, "document", f"{who} uploaded '{doc.name}'.")
        if f:
            doc_ai.process(doc)
            miss = doc.check_result.get("missing") or []
            log(case, request.user, "document", f"Automatic check of '{doc.name}': " + ("content looks complete." if not miss else "may be missing " + ", ".join(miss) + "."))
        return Response((ClientDocumentSerializer if role == "client" else DocumentSerializer)(doc).data, status=201)

    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        need(request.user, *STAFF)
        case = self.get_object()
        ser = PaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pay = ser.save(case=case, paid_by=request.data.get("paid_by") or case.third_party)
        log(case, request.user, "status", f"Recovered Rs {pay.amount} from {pay.paid_by or 'third party'} (remaining Rs {case.remaining_amount}).")
        if case.remaining_amount <= 0 and case.status != "Closed":
            case.status = "Recovered / Partially Recovered"
            case.save(update_fields=["status"])
        return Response(PaymentSerializer(pay).data, status=201)

    @action(detail=True, methods=["post"], url_path="third-party")
    def third_party(self, request, pk=None):
        need(request.user, *STAFF)
        case, d = self.get_object(), request.data
        if d.get("event_type") not in dict(ThirdPartyEvent.TYPES): raise ValidationError("Choose the type of response.")
        ev = ThirdPartyEvent.objects.create(case=case, event_type=d["event_type"], party=d.get("party") or case.third_party,
            reference_no=d.get("reference_no", ""), amount=money(d["amount"]) if d.get("amount") else None, note=d.get("note", ""),
            event_date=d.get("event_date") or date.today(), created_by=request.user)
        log(case, request.user, "third_party", f"{ev.party or 'Third party'}: {ev.get_event_type_display()}" + (f" (Rs {ev.amount})" if ev.amount else "") + (f". {ev.note}" if ev.note else ""))
        target = STAGE_FOR_EVENT.get(ev.event_type)
        if target and STATUSES.index(case.status) < STATUSES.index(target):
            log(case, request.user, "status", f"Status changed: {case.status} -> {target}")
            case.status = target
            case.save(update_fields=["status"])
        if d.get("next_followup_date"):
            case.next_followup_date = d["next_followup_date"]
            case.save(update_fields=["next_followup_date"])
        return Response(ThirdPartyEventSerializer(ev).data, status=201)

    @action(detail=True, methods=["post"], url_path="ai-summary")
    def ai_summary(self, request, pk=None):
        need(request.user, *STAFF)
        text, src = ai.summarize(self.get_object())
        return Response({"summary": text, "source": src})

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        q = (request.data.get("question") or "").strip()
        if not q: raise ValidationError("Question is required.")
        audience = "client" if role_of(request.user) == "client" else "staff"
        text, src = ai.ask(self.get_object(), q, audience)
        return Response({"answer": text, "source": src})

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        """Mixed claims file (CSV/XLSX): only claims flagged with subrogation potential become recovery cases."""
        need(request.user, "manager")
        f = request.FILES.get("file")
        if not f: raise ValidationError("Upload a CSV or Excel file.")
        try: rows = read_rows(f)
        except Exception as e: raise ValidationError(f"Could not read the file: {e}")
        if not rows: raise ValidationError("The file has no data rows.")
        flag_col = next((c for c in FLAG_COLS if c in rows[0]), None)
        mode = f"Column '{flag_col}'" if flag_col else "No subrogation column found - used rows that name a third party"
        res = {"total_rows": len(rows), "mode": mode, "normal_claims_ignored": 0, "duplicates": [], "errors": [], "imported_cases": []}
        for i, row in enumerate(rows, start=2):
            cid, third = pick(row, "claim_id", "claim_no", "claim_number"), pick(row, "third_party", "at_fault_party", "responsible_party")
            if not (pick(row, flag_col).lower() in YES if flag_col else bool(third)):
                res["normal_claims_ignored"] += 1
                continue
            try: amt = Decimal(re.sub(r"[^\d.]", "", pick(row, "amount_paid", "claim_amount", "paid_amount", "settled_amount")))
            except InvalidOperation:
                res["errors"].append(f"Row {i} ({cid or '?'}): amount missing or invalid"); continue
            if not cid:
                res["errors"].append(f"Row {i}: claim ID missing"); continue
            if RecoveryCase.objects.filter(claim_id=cid).exists():
                res["duplicates"].append(cid); continue
            c = RecoveryCase.objects.create(claim_id=cid, policyholder=pick(row, "policyholder", "customer_name", "customer", "insured") or "Unknown",
                incident_details=pick(row, "incident_details", "accident_details", "description"), third_party=third, amount_paid=amt,
                client=User.objects.filter(username=pick(row, "client_username", "client_login")).first())
            new_case_setup(c, request.user)
            log(c, request.user, "system", f"Imported from file '{f.name}' (subrogation potential identified).")
            res["imported_cases"].append({"id": c.id, "recovery_id": c.recovery_id, "claim_id": cid, "policyholder": c.policyholder})
        res["imported"] = len(res["imported_cases"])
        return Response(res)


# ---------------- documents ----------------
def get_doc(request, pk):
    doc = Document.objects.select_related("case").get(pk=pk)
    if not visible_cases(request.user).filter(pk=doc.case_id).exists(): raise PermissionDenied()
    return doc


@api_view(["PATCH", "DELETE"])
def document_detail(request, pk):
    need(request.user, *STAFF)
    doc = get_doc(request, pk)
    if request.method == "DELETE":
        need(request.user, "manager")
        doc.delete()
        return Response(status=204)
    st = request.data.get("status")
    if st in ("pending", "received"):
        doc.status = st
        doc.save()
        log(doc.case, request.user, "document", f"Document '{doc.name}' marked {st}.")
    return Response(DocumentSerializer(doc).data)


@api_view(["POST"])
def document_process(request, pk):
    need(request.user, *STAFF)
    doc = get_doc(request, pk)
    if not doc.file: raise ValidationError("Upload a file first.")
    return Response(DocumentSerializer(doc_ai.process(doc)).data)


# ---------------- monitoring, dashboard, third parties ----------------
@api_view(["GET"])
def alerts(request):
    need(request.user, *STAFF)
    items = get_alerts(request.user)
    if request.query_params.get("suggest") == "1":
        for i in items[:5]: i["suggestion"] = ai.suggest_action(i)
    return Response(items)


@api_view(["GET"])
def dashboard(request):
    need(request.user, *STAFF)
    qs = visible_cases(request.user)
    cnt = {s: qs.filter(status=s).count() for s in STATUSES}
    rec = Payment.objects.filter(case__in=qs).aggregate(t=Sum("amount"))["t"] or 0
    exp = qs.aggregate(t=Sum("expected_recovery"))["t"] or 0
    delayed = [a for a in get_alerts(request.user) if a["inactive_days"] >= 14 or a["overdue"]]
    emp = []
    for u in User.objects.all():
        mine = qs.filter(assigned_to=u)
        if not mine.exists(): continue
        r = Payment.objects.filter(case__in=mine).aggregate(t=Sum("amount"))["t"] or 0
        e = mine.aggregate(t=Sum("expected_recovery"))["t"] or 0
        emp.append({"employee": u.username, "total": mine.count(), "open": mine.exclude(status__in=OPEN_EXCLUDED).count(),
                    "closed": mine.filter(status__in=OPEN_EXCLUDED).count(),
                    "delayed": sum(1 for a in delayed if a["assigned_to"] == u.username), "expected": e, "recovered": r})
    uploads = Document.objects.filter(case__in=qs, uploaded_by__profile__role="client").exclude(file="") \
        .select_related("case", "uploaded_by").order_by("-uploaded_at")[:6]
    return Response({"total_cases": qs.count(), "by_status": cnt, "new_cases": cnt["New Case"],
                     "under_investigation": cnt["Under Investigation"], "awaiting_response": cnt["Awaiting Response"],
                     "delayed_cases": len(delayed), "completed_cases": qs.filter(status__in=OPEN_EXCLUDED).count(),
                     "expected_total": exp, "recovered_total": rec, "remaining_total": exp - rec, "employees": emp,
                     "client_uploads": [{"id": d.id, "case": d.case_id, "recovery_id": d.case.recovery_id, "policyholder": d.case.policyholder,
                                         "name": d.name, "uploaded_at": d.uploaded_at, "complete": d.check_result.get("complete"),
                                         "summary": (d.ai_summary or "")[:160]} for d in uploads]})


@api_view(["GET"])
def third_parties(request):
    """Insurer-wise view of responses, amounts claimed and amounts recovered."""
    need(request.user, *STAFF)
    groups, totals = {}, {"paid_by_us": Decimal(0), "claimed": Decimal(0), "recovered": Decimal(0)}
    cases = visible_cases(request.user).exclude(third_party="").prefetch_related("tp_events", "payments")
    for c in cases:
        evs = list(c.tp_events.all())
        latest = evs[0] if evs else None
        replies = [e for e in evs if e.event_type not in ("request_sent", "info_sent")]
        rec = sum((p.amount for p in c.payments.all()), Decimal(0))
        g = groups.setdefault(c.third_party.strip(), {"party": c.third_party.strip(), "cases": [], "paid_by_us": Decimal(0), "claimed": Decimal(0),
                                                       "recovered": Decimal(0), "awaiting": 0, "last_response": None})
        g["cases"].append({"id": c.id, "recovery_id": c.recovery_id, "policyholder": c.policyholder, "status": c.status,
                           "stage": latest.get_event_type_display() if latest else "Request not sent", "last_update": latest.event_date if latest else None,
                           "offer": next((e.amount for e in evs if e.event_type == "offer" and e.amount), None),
                           "claimed": c.expected_recovery, "recovered": rec, "remaining": c.expected_recovery - rec})
        g["paid_by_us"] += c.amount_paid; g["claimed"] += c.expected_recovery; g["recovered"] += rec
        if c.status == "Awaiting Response": g["awaiting"] += 1
        if replies and (g["last_response"] is None or replies[0].event_date > g["last_response"]): g["last_response"] = replies[0].event_date
        totals["paid_by_us"] += c.amount_paid; totals["claimed"] += c.expected_recovery; totals["recovered"] += rec
    parties = sorted(groups.values(), key=lambda g: g["recovered"] - g["claimed"])
    for g in parties: g["outstanding"] = g["claimed"] - g["recovered"]
    totals["outstanding"] = totals["claimed"] - totals["recovered"]
    return Response({"totals": totals, "parties": parties})


# ---------------- AI agent ----------------
@api_view(["POST"])
def agent_run(request):
    need(request.user, *STAFF)
    return Response(AgentRunSerializer(agent.run_agent(request.user, request.data.get("instruction", ""))).data)


@api_view(["GET"])
def agent_latest(request):
    need(request.user, *STAFF)
    run = AgentRun.objects.filter(created_by=request.user).first()
    return Response(AgentRunSerializer(run).data if run else {})


@api_view(["POST"])
def finding_respond(request, pk):
    need(request.user, *STAFF)
    fd = AgentFinding.objects.select_related("case").get(pk=pk)
    if not visible_cases(request.user).filter(pk=fd.case_id).exists(): raise PermissionDenied()
    act, note, nxt = request.data.get("action"), (request.data.get("note") or "").strip(), request.data.get("next_followup_date") or None
    labels = {"accept": ("accepted", "Accepted the recommendation"), "done": ("done", "Completed the recommended action"),
              "snooze": ("snoozed", "Snoozed the recommendation"), "dismiss": ("dismissed", "Dismissed the recommendation")}
    if act not in labels: raise ValidationError("Unknown action.")
    if act in ("done", "dismiss") and not note: raise ValidationError("Add a short note explaining what was done or why it is dismissed.")
    if act == "snooze" and not nxt: raise ValidationError("Pick the date to be reminded again.")
    fd.status, fd.employee_note, fd.responded_by, fd.responded_at = labels[act][0], note, request.user, timezone.now()
    fd.save()
    if nxt:
        fd.case.next_followup_date = nxt
        fd.case.save(update_fields=["next_followup_date"])
    log(fd.case, request.user, "followup" if act in ("accept", "done") else "note",
        f"AI agent suggested: {fd.suggested_action} | Employee response: {labels[act][1]}." + (f" {note}" if note else ""))
    return Response(AgentFindingSerializer(fd).data)
