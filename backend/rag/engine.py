"""Retrieval-Augmented Generation for case documents and records.
Sentence Transformers embeds the text, ChromaDB stores and searches it, Qwen3 (Ollama) writes the answer from the retrieved passages."""
import hashlib, json, os, re, threading
from pathlib import Path
from django.conf import settings
from cases import ai
from cases.access import visible_cases
from cases.models import RecoveryCase

STORE = Path(settings.BASE_DIR) / "rag_store"
MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K = int(os.getenv("RAG_TOP_K", "6"))
SYSTEM = ("You answer questions for an insurance subrogation recovery team using ONLY the numbered sources provided. "
          "Cite the sources you use like [1] or [2][3]. If the sources do not contain the answer, say what is missing. Be concise and factual.")
_lock = threading.Lock()
_cache = {}


class RagUnavailable(Exception):
    pass


def _model():
    if "model" not in _cache:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RagUnavailable("RAG packages are not installed. Run: pip install -r requirements-rag.txt")
        _cache["model"] = SentenceTransformer(MODEL_NAME)
    return _cache["model"]


def _collection():
    if "col" not in _cache:
        try:
            import chromadb
        except ImportError:
            raise RagUnavailable("RAG packages are not installed. Run: pip install -r requirements-rag.txt")
        STORE.mkdir(parents=True, exist_ok=True)
        _cache["col"] = chromadb.PersistentClient(path=str(STORE)).get_or_create_collection("subrotrack_cases", metadata={"hnsw:space": "cosine"})
    return _cache["col"]


def embed(texts):
    return _model().encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def split(text, size=800, overlap=120):
    text, out, i = re.sub(r"\s+", " ", text or "").strip(), [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


def case_chunks(c):
    """Everything searchable about one case: record facts, evidence list, document text, activity, insurer updates, payments."""
    rid, out = c.recovery_id, []

    def add(kind, name, text, key):
        out.append({"id": f"c{c.id}-{key}", "text": f"[{rid} | {name}] {text}",
                    "meta": {"case_id": c.id, "recovery_id": rid, "source_type": kind, "source_name": name}})

    add("case_record", "Case overview", f"Case {rid} for claim {c.claim_id}, policyholder {c.policyholder}. Status: {c.status}. Third party: {c.third_party or 'n/a'}. "
        f"Incident: {c.incident_details or 'n/a'}. Paid by insurer Rs {c.amount_paid}; expected recovery Rs {c.expected_recovery}; "
        f"recovered Rs {c.amount_recovered}; remaining Rs {c.remaining_amount}. Next follow-up: {c.next_followup_date or 'not set'}.", "overview")
    docs = list(c.documents.all())
    add("case_record", "Evidence checklist", "Evidence and documents for this case: " + "; ".join(
        f"{d.name} is {d.status}" + (f" (uploaded by {d.uploaded_by.username})" if d.uploaded_by_id else "") +
        (f", content issues: {', '.join(d.check_result['missing'])}" if d.check_result.get("missing") else "") for d in docs), "evidence")
    for d in docs:
        if d.ai_summary:
            add("document", d.name, f"Summary of {d.name}: {d.ai_summary} Extracted details: {json.dumps(d.extracted_details)}", f"d{d.id}-sum")
        for i, part in enumerate(split(d.extracted_text)):
            add("document", d.name, part, f"d{d.id}-{i}")
    acts = [f"{a.created_at:%d %b %Y} ({a.type}): {a.description}" for a in c.activities.all()]
    for i in range(0, len(acts), 6):
        add("activity", "Activity log", " | ".join(acts[i:i + 6]), f"act{i}")
    events = [f"{e.event_date:%d %b %Y} {e.party or 'third party'}: {e.get_event_type_display()}" + (f" Rs {e.amount}" if e.amount else "") + (f" - {e.note}" if e.note else "")
              for e in c.tp_events.all()]
    if events:
        add("third_party", "Third-party insurer updates", " | ".join(events), "tp")
    pays = [f"{p.date:%d %b %Y} Rs {p.amount} from {p.paid_by or 'third party'}" for p in c.payments.all()]
    if pays:
        add("payment", "Payments received", " | ".join(pays), "pay")
    return out


def fingerprint(c):
    raw = json.dumps([c.status, c.third_party, c.incident_details, str(c.amount_paid), str(c.expected_recovery), str(c.next_followup_date),
                      [(d.id, d.status, str(d.processed_at), len(d.extracted_text)) for d in c.documents.all()],
                      [a.id for a in c.activities.all()], [e.id for e in c.tp_events.all()], [(p.id, str(p.amount)) for p in c.payments.all()]])
    return hashlib.md5(raw.encode()).hexdigest()


def _fps():
    try:
        return json.loads((STORE / "fingerprints.json").read_text())
    except Exception:
        return {}


def sync(cases, force=False):
    """Re-index only the cases that changed since they were last indexed (new upload, new activity, payment ...)."""
    col, fps, n = _collection(), _fps(), 0
    for c in cases:
        fp = fingerprint(c)
        if not force and fps.get(str(c.id)) == fp:
            continue
        col.delete(where={"case_id": c.id})
        chunks = case_chunks(c)
        col.add(ids=[x["id"] for x in chunks], documents=[x["text"] for x in chunks], embeddings=embed([x["text"] for x in chunks]), metadatas=[x["meta"] for x in chunks])
        fps[str(c.id)] = fp
        n += 1
    if n:
        (STORE / "fingerprints.json").write_text(json.dumps(fps))
    return n


def _with_related(qs):
    return qs.select_related("assigned_to").prefetch_related("documents__uploaded_by", "activities", "payments", "tp_events")


def reindex_all():
    with _lock:
        return sync(list(_with_related(RecoveryCase.objects.all())), force=True)


def status():
    try:
        return {"ready": True, "chunks": _collection().count(), "model": MODEL_NAME, "cases_indexed": len(_fps())}
    except RagUnavailable as e:
        return {"ready": False, "message": str(e)}


def answer(user, question, case_id=None):
    qs = _with_related(visible_cases(user))
    if case_id:
        qs = qs.filter(pk=case_id)
    else:
        ids = [x.upper() for x in re.findall(r"SUB-\d+", question, re.I)]
        if ids:
            qs = qs.filter(recovery_id__in=ids)
    cases = list(qs)
    if not cases:
        return {"answer": "I could not find a matching case that you have access to.", "sources": [], "mode": "none"}
    with _lock:
        sync(cases)
    col = _collection()
    where = {"case_id": cases[0].id} if len(cases) == 1 else {"case_id": {"$in": [c.id for c in cases]}}
    hits = col.query(query_embeddings=embed([question]), n_results=TOP_K + (0 if len(cases) == 1 else 3), where=where)
    sources = [{"n": i + 1, "case_id": m["case_id"], "recovery_id": m["recovery_id"], "source_type": m["source_type"], "source_name": m["source_name"],
                "score": round(max(0.0, 1 - dist) * 100), "snippet": doc}
               for i, (doc, m, dist) in enumerate(zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0]))]
    if not sources:
        return {"answer": "No indexed information was found for this question.", "sources": [], "mode": "none"}
    context = "\n\n".join(f"[{s['n']}] {s['recovery_id']} - {s['source_name']} ({s['source_type']})\n{s['snippet'][:900]}" for s in sources)
    try:
        text, mode = ai.ask_llm(f"Sources:\n{context}\n\nQuestion: {question}", system=SYSTEM), "ollama"
    except Exception:
        text, mode = "The AI model is offline, so here are the most relevant excerpts instead. See the sources below.", "retrieval-only"
    return {"answer": text, "sources": sources, "mode": mode, "cases": [c.recovery_id for c in cases]}
