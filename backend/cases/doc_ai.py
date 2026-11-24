"""AI document processing: PyMuPDF text extraction -> Qwen3 summary + detail extraction ->
rule-based check of the content against what each document type must contain."""
import json, re
from django.utils import timezone
from . import ai

DATE = r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+\d{4})\b"
AMT = r"(₹|rs\.?|inr)\s*[\d,]+(\.\d+)?"
VEH = r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{4}\b"
# (label, regex, flags)
REQ = {
    "accident": [("Date of incident", DATE, re.I), ("Location of incident", r"(location|place of|\bat\b.{0,40}(road|highway|junction|nagar|street|chowk))", re.I),
                 ("Vehicles / parties involved", r"(vehicle|registration|driver|party|parties|" + VEH + ")", 0),
                 ("Police report / FIR number", r"(\bfir\b|police|report no|complaint no)", re.I),
                 ("Description of how it happened", r"(collision|collided|hit|rear-ended|skid|overturn|description|narrative|damage)", re.I)],
    "repair": [("Invoice / bill number", r"(invoice|bill)\s*(no|number|#)", re.I), ("Total amount", AMT, re.I),
               ("Garage / workshop name", r"(garage|workshop|motors|service cent|auto|body shop)", re.I),
               ("Vehicle registration", VEH, 0), ("Date", DATE, re.I)],
    "payment": [("Transaction / UTR / reference", r"(utr|transaction|txn|reference|ref\.? no|cheque|neft|rtgs|imps|upi)", re.I),
                ("Amount", AMT, re.I), ("Date", DATE, re.I), ("Bank / payer details", r"(bank|paid by|payer|account)", re.I)],
}
IMG = ("jpg", "jpeg", "png", "webp")


def doc_kind(name):
    n = name.lower()
    for k, keys in (("accident", ("accident", "fir", "police", "incident")), ("repair", ("repair", "bill", "invoice", "estimate")),
                    ("payment", ("payment", "receipt", "utr")), ("photo", ("photo", "image", "picture"))):
        if any(x in n for x in keys): return k
    return "other"


def extract_text(path, filename):
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        import fitz  # PyMuPDF
        with fitz.open(path) as pdf:
            return "\n".join(page.get_text() for page in pdf).strip()
    if ext in ("txt", "md", "csv"):
        return open(path, encoding="utf-8", errors="ignore").read().strip()
    return ""


def regex_details(text):
    uniq = lambda l: list(dict.fromkeys(l))[:5]
    return {"dates": uniq([m.group(0) for m in re.finditer(DATE, text, re.I)]),
            "amounts": uniq([m.group(0) for m in re.finditer(AMT + r"|\b[\d,]{5,}\.\d{2}\b", text, re.I)]),
            "vehicle_numbers": uniq(re.findall(VEH, text)),
            "reference_numbers": uniq(re.findall(r"\b(?:FIR|CLM|INV|UTR|TXN)[-\s#:]*[A-Z0-9/-]{3,}\b", text, re.I))}


def check_content(kind, text, filename):
    ext = filename.lower().rsplit(".", 1)[-1]
    if kind == "photo":
        ok = ext in IMG
        return {"complete": ok, "items": [{"item": "Image file (jpg/png)", "found": ok}], "missing": [] if ok else ["Image file (jpg/png)"],
                "note": "Photos are accepted as evidence; image content is not analysed."}
    reqs = REQ.get(kind) or [("Readable text", r"\S", 0)]
    items = [{"item": l, "found": bool(re.search(p, text, f))} for l, p, f in reqs]
    missing = [i["item"] for i in items if not i["found"]]
    return {"complete": not missing, "items": items, "missing": missing, "note": ""}


def _fallback_summary(text):
    return " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:3])[:450]


def process(doc):
    """Analyse one Document that has a file. Saves and returns the document."""
    name = doc.file.name.split("/")[-1]
    kind = doc_kind(doc.name)
    try:
        text = extract_text(doc.file.path, name)
        err = ""
    except Exception as e:
        text, err = "", f"Could not read the file: {e}"
    doc.extracted_text = text[:20000]
    doc.check_result = check_content(kind, text, name)
    doc.processed_at = timezone.now()
    if kind == "photo":
        doc.ai_summary, doc.extracted_details, doc.ai_source = "Photograph received.", {}, "rules"
    elif not text:
        doc.ai_summary = err or "No readable text found. This looks like a scanned image or an unsupported file - upload a text PDF or review it manually."
        doc.extracted_details, doc.ai_source = {}, "rules"
        doc.check_result["complete"] = False
        doc.check_result["note"] = "Content could not be verified."
    else:
        body = text[:5000]
        details = regex_details(text)
        try:
            doc.ai_summary = ai.ask_llm(f"Expected document type: {doc.name}.\nDocument text:\n{body}\n\n"
                "Summarise this document in 3 short sentences, then add one line starting 'Purpose:' saying what it proves in the recovery case.",
                system="You summarise insurance documents accurately and briefly. Use only the text given.")
            raw = json.loads(ai.ask_llm("Document text:\n" + body + "\n\nReturn JSON with keys: incident_date, location, parties (list), "
                "amount, reference_numbers (list), key_facts (list of at most 3 short strings). Use null when absent.",
                system="You extract fields from insurance documents. Output JSON only. Never invent values.", json_mode=True))
            details = {**{k: v for k, v in raw.items() if v}, **{k: v for k, v in details.items() if v and k not in raw}}
            doc.ai_source = "ollama"
        except Exception:
            doc.ai_summary, doc.ai_source = _fallback_summary(text) + "\n(Ollama unavailable - first lines of the document shown.)", "rules"
        doc.extracted_details = details
    doc.save()
    return doc
