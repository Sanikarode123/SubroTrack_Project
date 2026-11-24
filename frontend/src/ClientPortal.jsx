import React, { useEffect, useState } from "react";
import { FolderOpen, FileWarning, Wallet, CheckCircle2, Upload } from "lucide-react";
import { api, inr, fmtDate, STATUSES } from "./api.js";
import AskAI from "./AskAI.jsx";
import { CaseThirdParty } from "./ThirdParty.jsx";

function Stepper({ status }) {
  const at = STATUSES.indexOf(status);
  return (
    <ol className="flex flex-wrap gap-x-1 gap-y-2">
      {STATUSES.map((s, i) => (
        <li key={s} className="flex items-center gap-1.5 text-xs">
          <span className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold ${i < at ? "bg-teal-600 text-white" : i === at ? "bg-teal-100 text-teal-700 ring-2 ring-teal-600" : "bg-slate-100 text-slate-400"}`}>{i < at ? "✓" : i + 1}</span>
          <span className={i === at ? "font-semibold text-teal-700" : i < at ? "text-slate-700" : "text-slate-400"}>{s}</span>
          {i < STATUSES.length - 1 && <span className="mx-1 hidden h-px w-4 bg-slate-200 md:block" />}
        </li>))}
    </ol>
  );
}

const Tile = ({ icon: Icon, label, value }) => (
  <div className="card p-4"><div className="flex items-center gap-2 text-sm text-slate-600"><span className="grid h-7 w-7 place-items-center rounded-lg bg-teal-100 text-teal-700"><Icon size={15} /></span>{label}</div>
    <div className="mt-2 text-2xl font-semibold">{value}</div></div>
);

export function ClientHome({ user, open }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { api("/cases/").then(setRows); }, []);
  if (!rows) return <p>Loading…</p>;
  const missing = rows.reduce((n, c) => n + c.missing_documents.length, 0);
  const sum = (k) => rows.reduce((n, c) => n + Number(c[k] || 0), 0);
  return (
    <div className="space-y-5">
      <div><h1 className="text-xl font-semibold">Welcome, {user.name}</h1><p className="text-sm text-slate-500">Your claims that are being recovered from the responsible party, and what we need from you.</p></div>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Tile icon={FolderOpen} label="Your claims" value={rows.length} /><Tile icon={FileWarning} label="Documents needed" value={missing} />
        <Tile icon={Wallet} label="Paid to you" value={inr(sum("amount_paid"))} /><Tile icon={CheckCircle2} label="Recovered so far" value={inr(sum("amount_recovered"))} />
      </div>
      {rows.length === 0 && <p className="card p-6 text-center text-sm text-slate-500">No recovery cases are linked to your account yet.</p>}
      <div className="space-y-3">
        {rows.map((c) => (
          <div key={c.id} className="card space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2"><b className="text-lg">{c.recovery_id}</b><span className="text-sm text-slate-500">Claim {c.claim_id} · against {c.third_party || "third party"}</span>
              <button className="btn ml-auto" onClick={() => open(c.id)}>View & upload</button></div>
            <Stepper status={c.status} />
            {c.missing_documents.length > 0
              ? <p className="rounded-lg bg-amber-50 p-2.5 text-sm text-amber-900"><b>Please upload:</b> {c.missing_documents.join(", ")}</p>
              : <p className="text-sm text-emerald-700">All required documents received.</p>}
          </div>))}
      </div>
    </div>
  );
}

export function ClientCase({ id, back }) {
  const [c, setC] = useState(null); const [tab, setTab] = useState("Progress"); const [busy, setBusy] = useState(null); const [err, setErr] = useState(""); const [other, setOther] = useState("");
  const load = () => api(`/cases/${id}/`).then(setC);
  useEffect(() => { load(); }, [id]);
  if (!c) return <p>Loading…</p>;
  const upload = async (name, file, key) => {
    const form = new FormData(); form.append("name", name); form.append("file", file); setBusy(key); setErr("");
    try { await api(`/cases/${id}/documents/`, { method: "POST", form }); setOther(""); await load(); } catch (e) { setErr(e.message); } finally { setBusy(null); }
  };
  return (
    <div className="space-y-4">
      <button className="text-sm text-teal-700 underline" onClick={back}>Back to my claims</button>
      <div className="flex flex-wrap items-center gap-3"><h1 className="text-xl font-semibold">{c.recovery_id}</h1><span className="text-slate-500">Claim {c.claim_id}</span><span className="chip bg-teal-100 text-teal-700">{c.status}</span></div>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {["Progress", "Documents", "Insurer updates", "Ask a question"].map((t) => <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-teal-600 font-semibold" : "text-slate-600"}`}>{t}</button>)}
      </div>
      {tab === "Progress" && (
        <div className="space-y-4">
          <div className="card p-4"><Stepper status={c.status} /></div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[["Paid to you", c.amount_paid], ["Being recovered", c.expected_recovery], ["Recovered so far", c.amount_recovered], ["Still to recover", c.remaining_amount]].map(([l, v]) => (
            <div key={l} className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-lg font-semibold">{inr(v)}</div></div>))}</div>
          <div className="card p-4 text-sm"><b>Incident:</b> {c.incident_details || "—"}</div>
          <ol className="card divide-y divide-slate-100">{c.timeline.length === 0 && <li className="p-4 text-sm text-slate-500">No updates yet.</li>}
            {c.timeline.map((a) => <li key={a.id} className="p-3 text-sm"><div className="text-xs text-slate-500">{fmtDate(a.created_at)}</div>{a.description}</li>)}</ol>
        </div>)}
      {tab === "Documents" && (
        <div className="space-y-3">
          {err && <p className="text-sm text-red-700">{err}</p>}
          {c.documents.map((d) => (
            <div key={d.id} className={`card flex flex-wrap items-center gap-3 p-3 text-sm ${d.status === "pending" ? "border-amber-300" : ""}`}>
              <b className="min-w-[10rem]">{d.name}</b>
              <span className={`chip ${d.status === "received" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{d.status === "received" ? "Received" : "Needed from you"}</span>
              {d.issues.length > 0 && <span className="text-xs text-amber-800">This file may be missing: {d.issues.join(", ")}. Please check and upload again.</span>}
              <label className="btn-ghost ml-auto cursor-pointer"><Upload size={14} />{busy === d.id ? "Uploading…" : d.status === "received" ? "Replace" : "Upload"}
                <input type="file" hidden onChange={(e) => e.target.files[0] && upload(d.name, e.target.files[0], d.id)} /></label>
            </div>))}
          <div className="card flex flex-wrap items-end gap-2 p-4">
            <div className="min-w-[14rem] flex-1"><label className="label">Other document</label><input className="input" placeholder="e.g. Driving licence" value={other} onChange={(e) => setOther(e.target.value)} /></div>
            <label className={`btn cursor-pointer ${other ? "" : "pointer-events-none opacity-50"}`}>{busy === "new" ? "Uploading…" : "Choose file & upload"}<input type="file" hidden onChange={(e) => e.target.files[0] && upload(other, e.target.files[0], "new")} /></label>
          </div>
          <p className="text-xs text-slate-500">PDF files work best. Our team is notified as soon as you upload.</p>
        </div>)}
      {tab === "Insurer updates" && <CaseThirdParty c={c} reload={load} canEdit={false} />}
      {tab === "Ask a question" && <AskAI caseId={c.id} staff={false} suggestions={["What is the status of my claim?", "Which documents are missing?", "How much has been recovered?", "What happens next?"]} />}
    </div>
  );
}
