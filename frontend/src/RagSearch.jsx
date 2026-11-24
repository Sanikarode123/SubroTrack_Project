import React, { useState } from "react";
import { FileSearch } from "lucide-react";
import { api } from "./api.js";

const kind = { document: "Document", case_record: "Case record", activity: "Activity", third_party: "Insurer update", payment: "Payment" };

// numbered references shown under every answer so staff can verify it
export function Sources({ sources, open }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-xs font-medium text-slate-500">Sources</div>
      {sources.map((s) => (
        <details key={s.n} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs">
          <summary className="cursor-pointer">
            <b>[{s.n}]</b> {open ? <button type="button" className="text-teal-700 underline" onClick={(e) => { e.preventDefault(); open(s.case_id); }}>{s.recovery_id}</button> : s.recovery_id} · {s.source_name}
            <span className="chip ml-2 bg-slate-100 text-slate-600">{kind[s.source_type] || s.source_type}</span>
            <span className="ml-2 text-slate-400">match {s.score}%</span>
          </summary>
          <p className="mt-1 whitespace-pre-wrap text-slate-600">{s.snippet}</p>
        </details>))}
    </div>
  );
}

const EXAMPLES = ["What evidence is available to support recovery in case SUB-1003?", "Which documents are missing or incomplete for SUB-1001?", "What did the third-party insurer say about SUB-1002?"];

export default function RagSearch({ open }) {
  const [q, setQ] = useState(""); const [busy, setBusy] = useState(false); const [out, setOut] = useState(null); const [err, setErr] = useState("");
  const ask = async (text) => {
    if (!text.trim()) return;
    setQ(text); setBusy(true); setErr(""); setOut(null);
    try { setOut(await api("/rag/ask/", { method: "POST", body: { question: text } })); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-5">
      <div><h1 className="flex items-center gap-2 text-xl font-semibold"><FileSearch size={20} className="text-teal-600" />Evidence search</h1>
        <p className="text-sm text-slate-500">Ask a question in plain language. SubroTrack finds the relevant passages in uploaded documents and case records, and the AI answers from them with references. Mention a case ID such as SUB-1003 to focus on one case.</p></div>
      <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="card flex flex-wrap gap-2 p-4">
        <input className="input min-w-[16rem] flex-1" placeholder="e.g. What evidence supports recovery in case SUB-1003?" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn" disabled={busy}>{busy ? "Searching…" : "Search & answer"}</button>
      </form>
      <div className="flex flex-wrap gap-2">{EXAMPLES.map((x) => <button key={x} className="btn-ghost text-left" disabled={busy} onClick={() => ask(x)}>{x}</button>)}</div>
      {busy && <p className="text-sm text-slate-500">Retrieving documents and writing the answer. The first search of a new case builds its index and can take a little longer.</p>}
      {err && <p className="card border-red-200 p-3 text-sm text-red-700">{err}</p>}
      {out && (
        <div className="card p-4">
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold">Answer
            <span className="chip bg-slate-100 text-slate-500">{out.mode === "ollama" ? "Qwen3" : out.mode === "retrieval-only" ? "excerpts only" : "no result"}</span></div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{out.answer}</p>
          <Sources sources={out.sources} open={open} />
        </div>)}
    </div>
  );
}
