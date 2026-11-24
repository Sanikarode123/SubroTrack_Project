import React, { useState } from "react";
import { api } from "./api.js";
import { Sources } from "./RagSearch.jsx";

export default function AskAI({ caseId, staff, suggestions }) {
  const [summary, setSummary] = useState(null); const [busy, setBusy] = useState(false);
  const [q, setQ] = useState(""); const [chat, setChat] = useState([]);
  const [useRag, setUseRag] = useState(true);
  const gen = async () => { setBusy(true); try { setSummary(await api(`/cases/${caseId}/ai-summary/`, { method: "POST" })); } finally { setBusy(false); } };
  const ask = async (text) => {
    if (!text.trim()) return;
    setChat((h) => [...h, { role: "you", text }]); setQ(""); setBusy(true);
    let note = "";
    try {
      if (staff && useRag) {  // retrieval first: answer from the case's documents and records, with references
        try {
          const r = await api("/rag/ask/", { method: "POST", body: { question: text, case_id: caseId } });
          setChat((h) => [...h, { role: "ai", text: r.answer, sources: r.sources }]);
          return;
        } catch (e) { note = `(Document search unavailable: ${e.message} Showing the standard answer.)\n`; }
      }
      const r = await api(`/cases/${caseId}/ask/`, { method: "POST", body: { question: text } });
      setChat((h) => [...h, { role: "ai", text: note + r.answer }]);
    } catch (e) { setChat((h) => [...h, { role: "ai", text: e.message }]); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      {staff && (
        <div className="card p-4">
          <button className="btn" onClick={gen} disabled={busy}>{busy ? "Working…" : "Generate AI summary"}</button>
          {summary && <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-relaxed">{summary.summary}</pre>}
        </div>)}
      <div className="card space-y-3 p-4">
        {staff && <label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />Answer from this case's documents and records (shows sources)</label>}
        <div className="flex flex-wrap gap-2">{suggestions.map((s) => <button key={s} className="btn-ghost" disabled={busy} onClick={() => ask(s)}>{s}</button>)}</div>
        {chat.map((m, i) => (
          <div key={i} className={`rounded-lg p-3 text-sm ${m.role === "you" ? "bg-slate-100" : "whitespace-pre-wrap bg-teal-50"}`}>
            <b>{m.role === "you" ? "You" : "Assistant"}:</b> {m.text}
            {m.sources && <Sources sources={m.sources} />}
          </div>))}
        <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="flex gap-2">
          <input className="input" placeholder="Ask about this claim" value={q} onChange={(e) => setQ(e.target.value)} /><button className="btn" disabled={busy}>{busy ? "…" : "Ask"}</button></form>
      </div>
    </div>
  );
}
