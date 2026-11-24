"""Delayed-case AI agent. The Python rule engine (services.case_alert) stays the source of truth for dates and scores.
The agent calls monitoring tools over every open case, then asks Qwen3 to explain each flagged case and suggest the next
action. The employee's response to each recommendation is recorded in views.finding_respond."""
import json
from . import ai
from .models import AgentRun, AgentFinding
from .access import visible_cases
from .services import case_alert, OPEN_EXCLUDED
from .models import RecoveryCase

DEFAULT = "Check all pending recovery cases and tell me which cases need attention."


# ---- tools the agent calls ----
def get_pending_cases(user):
    qs = RecoveryCase.objects.exclude(status__in=OPEN_EXCLUDED).select_related("assigned_to").prefetch_related("documents", "activities")
    return list(qs.filter(pk__in=visible_cases(user).values("pk")))

def check_last_activity(c, a):
    return {"last_activity": c.last_activity_at.strftime("%d %b %Y"), "days_inactive": a["inactive_days"]}

def check_followup(c, a):
    return {"next_followup_date": str(c.next_followup_date) if c.next_followup_date else None, "overdue": a["overdue"]}

def check_documents(c, a):
    weak = [d.name for d in c.documents.all() if d.check_result and not d.check_result.get("complete", True)]
    return {"missing": a["missing_docs"], "uploaded_but_incomplete_content": weak}

def priority(score):
    return "High" if score >= 90 else "Medium" if score >= 50 else "Low"

def fallback_action(c, a, facts):
    steps = []
    if a["missing_docs"]: steps.append("collect " + ", ".join(a["missing_docs"]))
    if facts["documents"]["uploaded_but_incomplete_content"]: steps.append("re-check " + ", ".join(facts["documents"]["uploaded_but_incomplete_content"]))
    if a["overdue"] or a["inactive_days"] >= 7: steps.append(f"follow up with {c.third_party or 'the third party'} and log the response")
    return ("Please " + "; ".join(steps) + ".") if steps else "Review the case and update its activity log."


def run_agent(user, instruction=""):
    instruction = (instruction or "").strip() or DEFAULT
    cases = get_pending_cases(user)
    flagged = []
    for c in cases:
        a = case_alert(c)
        facts = {"activity": check_last_activity(c, a), "followup": check_followup(c, a), "documents": check_documents(c, a)}
        if a["reasons"]: flagged.append((c, a, facts))
    flagged.sort(key=lambda x: -x[1]["score"])

    ai_ok, items = True, []
    for i, (c, a, facts) in enumerate(flagged[:15]):
        reason = action = None; src = "rules"
        if ai_ok and i < 8:
            try:
                out = json.loads(ai.ask_llm(
                    f"Case {c.recovery_id}, status {c.status}, third party {c.third_party or 'unknown'}, Rs {c.remaining_amount} left to recover.\n"
                    f"Tool results: {json.dumps(facts)}\nIssues found: {'; '.join(a['reasons'])}.\n"
                    "Return JSON with keys 'reason' (one sentence on why this case needs attention) and 'next_action' (one concrete next step).",
                    json_mode=True))
                reason, action, src = str(out.get("reason") or ""), str(out.get("next_action") or ""), "ollama"
            except Exception:
                ai_ok = False
        items.append((c, a, reason or ("; ".join(a["reasons"]) + "."), action or fallback_action(c, a, facts),
                      "ollama" if reason and action else "rules"))

    high = sum(1 for x in items if priority(x[1]["score"]) == "High")
    lines = "\n".join(f"- {c.recovery_id} [{priority(a['score'])}]: {r}" for c, a, r, _, _ in items[:10])
    summary = (f"{len(items)} of {len(cases)} open cases need attention; {high} are high priority."
               + (f" Start with {items[0][0].recovery_id}: {items[0][2]}" if items else " Nothing is delayed right now."))
    if items and ai_ok:
        try:
            summary = ai.ask_llm(f"Employee request: {instruction}\nFindings:\n{lines}\n\nWrite a 3-sentence briefing: how many cases need attention, "
                                 "which to handle first and why.")
        except Exception:
            ai_ok = False

    trace = [{"tool": "get_pending_cases", "detail": f"Retrieved {len(cases)} open cases"},
             {"tool": "check_last_activity", "detail": f"Checked last activity on {len(cases)} cases"},
             {"tool": "check_followup", "detail": f"Checked follow-up dates on {len(cases)} cases"},
             {"tool": "check_documents", "detail": f"Checked required and AI-verified documents on {len(cases)} cases"},
             {"tool": "score_priority", "detail": f"{len(items)} cases flagged, {high} high priority"},
             {"tool": "explain_with_ai", "detail": "Qwen3 wrote the reasons and next actions" if ai_ok and items else "Ollama unavailable - rule-based wording used"}]
    AgentFinding.objects.filter(run__created_by=user, status="open").update(status="superseded")
    run = AgentRun.objects.create(created_by=user, instruction=instruction, summary=summary, tool_trace=trace,
                                  source="ollama" if ai_ok and items else "rules")
    AgentFinding.objects.bulk_create([AgentFinding(run=run, case=c, priority=priority(a["score"]), score=a["score"], level=a["level"],
        reasons=a["reasons"], reason=r, suggested_action=act, source=s) for c, a, r, act, s in items])
    return run
