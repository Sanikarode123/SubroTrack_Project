"""Prepares case context for the language model (Qwen3 via Ollama) and falls back to plain rules when it is offline."""
import json, urllib.request
from django.conf import settings
from .services import case_alert

SYSTEM = ("You are an assistant for an insurance subrogation recovery team. Answer ONLY from the case data given. "
          "If the data does not contain the answer, say so. Be short, clear and practical. Amounts are in Indian rupees.")
CLIENT_SYSTEM = ("You help a policyholder follow their insurance recovery case. Answer ONLY from the case data given, in simple, polite "
                 "language. Do not guess or promise outcomes. If the data does not contain the answer, say the insurer's team will update them.")
CLIENT_KINDS = ("status", "third_party", "document")


def build_context(case, audience="staff"):
    a = case_alert(case)
    client = audience == "client"
    acts = [x for x in case.activities.all() if not client or x.type in CLIENT_KINDS][:10]
    lines = [f"Recovery case {case.recovery_id} (claim {case.claim_id}). Status: {case.status}.",
             f"Policyholder: {case.policyholder}. Third party / insurer: {case.third_party or 'n/a'}.",
             f"Incident: {case.incident_details or 'n/a'}",
             f"Paid by our insurer: Rs {case.amount_paid}. Expected recovery: Rs {case.expected_recovery}. "
             f"Recovered so far: Rs {case.amount_recovered}. Remaining: Rs {case.remaining_amount}."]
    if not client:
        lines += [f"Next follow-up date: {case.next_followup_date or 'not set'}. Days since last activity: {a['inactive_days']}.",
                  "Delay flags: " + ("; ".join(a["reasons"]) or "none")]
    lines.append("Documents:")
    for d in case.documents.all():
        row = f"- {d.name}: {d.status}"
        if d.check_result and d.check_result.get("missing"):
            row += " | content issues: " + ", ".join(d.check_result["missing"])
        if not client and d.ai_summary:
            row += f" | summary: {d.ai_summary[:220]}"
        if not client and d.extracted_details:
            row += " | extracted: " + json.dumps(d.extracted_details)[:260]
        lines.append(row)
    lines.append("Third-party insurer activity (newest first):")
    lines += [f"- {e.event_date:%d %b %Y} {e.get_event_type_display()}" + (f" (Rs {e.amount})" if e.amount else "") + (f": {e.note}" if e.note else "")
              for e in list(case.tp_events.all())[:6]] or ["- none yet"]
    lines.append("Recent case activity (newest first):")
    lines += [f"- {x.created_at:%d %b %Y} [{x.type}] {x.description}" for x in acts] or ["- none"]
    return "\n".join(lines)


def ask_llm(prompt, system=SYSTEM, json_mode=False):
    body = json.dumps({"model": settings.OLLAMA_MODEL, "stream": False, "think": False,
                       **({"format": "json"} if json_mode else {}),
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                       "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(settings.OLLAMA_URL + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["message"]["content"].strip()


def fallback(case, audience="staff"):
    a = case_alert(case)
    pending = ", ".join(a["missing_docs"]) or "none"
    if audience == "client":
        return (f"Your claim {case.recovery_id} is currently at the stage '{case.status}'. Rs {case.amount_recovered} of Rs {case.expected_recovery} "
                f"has been recovered so far. Documents still needed from you: {pending}.\n\n(The AI assistant is offline, so this is a standard status message.)")
    steps = []
    if a["missing_docs"]: steps.append("Collect pending documents: " + pending)
    if a["overdue"] or a["inactive_days"] >= 7: steps.append("Follow up with the third party / their insurer")
    steps.append("Update the case activity after any response")
    return (f"{case.recovery_id}: status '{case.status}', Rs {case.amount_recovered} of Rs {case.expected_recovery} recovered "
            f"(Rs {case.remaining_amount} remaining).\nPending documents: {pending}.\nFlags: {'; '.join(a['reasons']) or 'none'}.\n"
            "Suggested next actions:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) + "\n\n(Ollama unavailable - rule-based answer shown.)")


def summarize(case):
    p = ("Case data:\n" + build_context(case) + "\n\nWrite: (1) a 3-sentence summary, (2) 'Pending items' as a list, "
         "(3) 'Suggested next actions' as a numbered list of at most 3.")
    try: return ask_llm(p), "ollama"
    except Exception: return fallback(case), "fallback"


def ask(case, question, audience="staff"):
    p = f"Case data:\n{build_context(case, audience)}\n\nQuestion: {question}"
    try: return ask_llm(p, CLIENT_SYSTEM if audience == "client" else SYSTEM), "ollama"
    except Exception: return fallback(case, audience), "fallback"


def suggest_action(item):
    p = (f"Case {item['recovery_id']}, status {item['status']}. Issues: {'; '.join(item['reasons'])}. "
         "Give ONE short suggested next action for the employee.")
    try: return ask_llm(p)
    except Exception:
        return "Contact the concerned party for an update and record it in the case activity."
