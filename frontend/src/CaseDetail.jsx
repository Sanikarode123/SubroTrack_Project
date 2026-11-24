import React, { useEffect, useState } from "react";
import { api, inr, fmtDate, levelClass, STATUSES } from "./api.js";
import Docs from "./DocsTab.jsx";
import AskAI from "./AskAI.jsx";
import { CaseThirdParty } from "./ThirdParty.jsx";

const TABS = ["Overview", "Activity", "Documents", "Third party", "Payments", "AI assistant"];

export default function CaseDetail({ id, back, user }) {
  const [c, setC] = useState(null); const [tab, setTab] = useState("Overview");
  const load = () => api(`/cases/${id}/`).then(setC);
  useEffect(() => { load(); }, [id]);
  if (!c) return <p>Loading…</p>;
  return (
    <div className="space-y-4">
      <button className="text-sm text-teal-700 underline" onClick={back}>Back to cases</button>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{c.recovery_id}</h1>
        <span className="text-slate-600">{c.policyholder} · claim {c.claim_id}</span>
        <span className={`chip ${levelClass(c.alert.level)}`}>{c.alert.level}</span>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-teal-600 font-semibold" : "text-slate-600"}`}>{t}</button>)}
      </div>
      {tab === "Overview" && <Overview c={c} reload={load} user={user} />}
      {tab === "Activity" && <Activity c={c} reload={load} />}
      {tab === "Documents" && <Docs c={c} reload={load} />}
      {tab === "Third party" && <CaseThirdParty c={c} reload={load} canEdit />}
      {tab === "Payments" && <Payments c={c} reload={load} />}
      {tab === "AI assistant" && <AskAI caseId={c.id} staff suggestions={["Why is this case delayed?", "What documents are pending?", "What details were extracted from the documents?", "What did the third-party insurer say?", "What should I do next?"]} />}
    </div>
  );
}

function Overview({ c, reload, user }) {
  const mgr = user.role === "manager";
  const [people, setPeople] = useState([]); const [err, setErr] = useState("");
  useEffect(() => { if (mgr) api("/users/").then(setPeople); }, []);
  const patch = (body) => { setErr(""); return api(`/cases/${c.id}/`, { method: "PATCH", body }).then(reload).catch((e) => setErr(e.message)); };
  const pick = (role) => people.filter((p) => p.role === role);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="card space-y-3 p-4">
        <div><label className="label">Status</label>
          <select className="input" value={c.status} onChange={(e) => patch({ status: e.target.value })}>{STATUSES.filter((s) => mgr || s !== "Closed" || c.status === s).map((s) => <option key={s}>{s}</option>)}</select></div>
        <div><label className="label">Next follow-up date</label>
          <input type="date" className="input" value={c.next_followup_date || ""} onChange={(e) => patch({ next_followup_date: e.target.value || null })} /></div>
        {mgr ? (<>
          <div><label className="label">Assigned employee</label>
            <select className="input" value={c.assigned_to || ""} onChange={(e) => patch({ assigned_to: e.target.value || null })}>
              <option value="">Unassigned</option>{pick("employee").concat(pick("manager")).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select></div>
          <div><label className="label">Client (can see this case in their portal)</label>
            <select className="input" value={c.client || ""} onChange={(e) => patch({ client: e.target.value || null })}>
              <option value="">Not linked</option>{pick("client").map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select></div>
        </>) : <p className="text-xs text-slate-500">Reassigning, closing a case and client linking are manager actions.</p>}
        {err && <p className="text-sm text-red-700">{err}</p>}
      </div>
      <div className="card space-y-1 p-4 text-sm">
        <p><b>Third party:</b> {c.third_party || "—"}</p>
        <p><b>Handled by:</b> {c.assigned_to_name || "Unassigned"} · <b>Client:</b> {c.client_name || "not linked"}</p>
        <p><b>Incident:</b> {c.incident_details || "—"}</p>
        <p><b>Paid by insurer:</b> {inr(c.amount_paid)}</p>
        <p><b>Expected recovery:</b> {inr(c.expected_recovery)}</p>
        <p><b>Recovered:</b> {inr(c.amount_recovered)}</p>
        <p><b>Remaining:</b> {inr(c.remaining_amount)}</p>
        {c.alert.reasons.length > 0 && <ul className="mt-2 list-disc rounded-lg bg-amber-50 p-2 pl-6 text-amber-900">{c.alert.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      </div>
    </div>
  );
}

function Activity({ c, reload }) {
  const [f, setF] = useState({ type: "note", description: "", next_followup_date: "" });
  const add = async (e) => { e.preventDefault(); await api(`/cases/${c.id}/activities/`, { method: "POST", body: f }); setF({ type: "note", description: "", next_followup_date: "" }); reload(); };
  return (
    <div className="space-y-4">
      <form onSubmit={add} className="card grid gap-3 p-4 md:grid-cols-4">
        <select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}><option value="note">Internal note</option><option value="followup">Follow-up done</option></select>
        <input className="input md:col-span-2" required placeholder="What happened?" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <input type="date" className="input" title="Next follow-up date" value={f.next_followup_date} onChange={(e) => setF({ ...f, next_followup_date: e.target.value })} />
        <div className="md:col-span-4"><button className="btn">Add activity</button> <span className="text-xs text-slate-500">Notes are internal; clients only see status, document and insurer updates.</span></div>
      </form>
      <ol className="card divide-y divide-slate-100">
        {c.activities.map((a) => <li key={a.id} className="p-3 text-sm"><div className="text-xs text-slate-500">{fmtDate(a.created_at)} · {a.type.replace("_", " ")} · {a.created_by_name}</div>{a.description}</li>)}
      </ol>
    </div>
  );
}

function Payments({ c, reload }) {
  const [f, setF] = useState({ amount: "", date: new Date().toISOString().slice(0, 10), paid_by: c.third_party || "", note: "" });
  const [err, setErr] = useState("");
  const add = async (e) => { e.preventDefault(); setErr("");
    try { await api(`/cases/${c.id}/payments/`, { method: "POST", body: f }); setF({ ...f, amount: "", note: "" }); reload(); } catch (x) { setErr(x.message); } };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        {[["Paid by our insurer", c.amount_paid], ["Expected", c.expected_recovery], ["Recovered", c.amount_recovered], ["Remaining", c.remaining_amount]].map(([l, v]) => (
          <div key={l} className="card p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-lg font-semibold">{inr(v)}</div></div>))}
      </div>
      <form onSubmit={add} className="card grid gap-3 p-4 md:grid-cols-5">
        <input className="input" type="number" step="0.01" required placeholder="Amount ₹" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
        <input className="input" type="date" required value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
        <input className="input" placeholder="Paid by" value={f.paid_by} onChange={(e) => setF({ ...f, paid_by: e.target.value })} />
        <input className="input" placeholder="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        <button className="btn">Record payment</button>{err && <p className="text-sm text-red-700 md:col-span-5">{err}</p>}
      </form>
      <div className="card divide-y divide-slate-100">
        {c.payments.length === 0 && <p className="p-4 text-sm text-slate-500">No payments recorded yet.</p>}
        {c.payments.map((p) => <div key={p.id} className="flex justify-between p-3 text-sm"><span>{fmtDate(p.date)} · {p.paid_by || "Payment"}{p.note && ` · ${p.note}`}</span><b>{inr(p.amount)}</b></div>)}
      </div>
    </div>
  );
}
