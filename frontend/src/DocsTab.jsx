import React, { useState } from "react";
import { CheckCircle2, XCircle, Sparkles, Upload } from "lucide-react";
import { api } from "./api.js";

function Analysis({ d }) {
  const cr = d.check_result || {}; const det = d.extracted_details || {};
  const rows = Object.entries(det).filter(([, v]) => v && (!Array.isArray(v) || v.length));
  return (
    <div className="mt-3 grid gap-3 rounded-xl bg-slate-50 p-3 text-sm md:grid-cols-2">
      <div className="md:col-span-2">
        <div className="mb-1 flex items-center gap-2 font-medium"><Sparkles size={14} className="text-teal-600" />AI summary
          <span className="chip bg-white text-slate-500">{d.ai_source === "ollama" ? "Qwen3" : "rule-based"}</span></div>
        <p className="whitespace-pre-wrap text-slate-700">{d.ai_summary}</p>
      </div>
      <div><div className="mb-1 font-medium">Requirement check</div>
        {(cr.items || []).map((i) => (<div key={i.item} className="flex items-center gap-2">
          {i.found ? <CheckCircle2 size={15} className="text-emerald-600" /> : <XCircle size={15} className="text-red-600" />}<span>{i.item}</span></div>))}
        <div className={`mt-2 chip ${cr.complete ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{cr.complete ? "Content looks complete" : "Needs attention: " + ((cr.missing || []).join(", ") || cr.note)}</div>
        {cr.note && cr.complete && <p className="mt-1 text-xs text-slate-500">{cr.note}</p>}
      </div>
      <div><div className="mb-1 font-medium">Extracted details</div>
        {rows.length === 0 && <p className="text-slate-500">Nothing extracted.</p>}
        {rows.map(([k, v]) => (<div key={k} className="text-slate-700"><span className="text-slate-500">{k.replace(/_/g, " ")}: </span>{Array.isArray(v) ? v.join(", ") : String(v)}</div>))}
      </div>
      {d.text_preview && <details className="md:col-span-2"><summary className="cursor-pointer text-xs text-slate-500">Show extracted text</summary>
        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap font-sans text-xs text-slate-600">{d.text_preview}</pre></details>}
    </div>
  );
}

export default function Docs({ c, reload }) {
  const [name, setName] = useState(""); const [busy, setBusy] = useState(null); const [err, setErr] = useState("");
  const upload = async (docName, file, id) => {
    const form = new FormData(); form.append("name", docName); form.append("file", file); setBusy(id || "new"); setErr("");
    try { await api(`/cases/${c.id}/documents/`, { method: "POST", form }); setName(""); await reload(); } catch (e) { setErr(e.message); } finally { setBusy(null); }
  };
  const analyze = async (d) => { setBusy(d.id); try { await api(`/documents/${d.id}/process/`, { method: "POST" }); await reload(); } finally { setBusy(null); } };
  const toggle = (d) => api(`/documents/${d.id}/`, { method: "PATCH", body: { status: d.status === "received" ? "pending" : "received" } }).then(reload);
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">Upload a PDF or text file. SubroTrack extracts the text, writes a short AI summary, pulls out key details and checks the content against what this document type must contain.</p>
      {err && <p className="text-sm text-red-700">{err}</p>}
      {c.documents.map((d) => (
        <div key={d.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <b className="min-w-[10rem]">{d.name}</b>
            <span className={`chip ${d.status === "received" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{d.status}</span>
            {d.uploaded_by_name && <span className="text-xs text-slate-500">uploaded by {d.uploaded_by_name}</span>}
            {d.file && <a className="text-teal-700 underline" href={d.file} target="_blank" rel="noreferrer">View file</a>}
            <div className="ml-auto flex flex-wrap gap-2">
              {d.file && <button className="btn-ghost" disabled={busy === d.id} onClick={() => analyze(d)}><Sparkles size={14} />Re-analyse</button>}
              <label className="btn-ghost cursor-pointer"><Upload size={14} />{busy === d.id ? "Analysing…" : "Upload"}<input type="file" hidden onChange={(e) => e.target.files[0] && upload(d.name, e.target.files[0], d.id)} /></label>
              <button className="btn-ghost" onClick={() => toggle(d)}>Mark {d.status === "received" ? "pending" : "received"}</button>
            </div>
          </div>
          {d.processed_at && <Analysis d={d} />}
        </div>))}
      <div className="card flex flex-wrap items-end gap-2 p-4">
        <div className="min-w-[14rem] flex-1"><label className="label">Add another document</label>
          <input className="input" placeholder="e.g. Police FIR" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <label className={`btn cursor-pointer ${name ? "" : "pointer-events-none opacity-50"}`}>{busy === "new" ? "Analysing…" : "Choose file & upload"}
          <input type="file" hidden onChange={(e) => e.target.files[0] && upload(name, e.target.files[0])} /></label>
      </div>
    </div>
  );
}
