import React, { useEffect, useState } from "react";
import { FolderOpen, Wallet, TrendingUp, AlertTriangle } from "lucide-react";
import { api, inr, levelClass } from "./api.js";

const Stat = ({ icon: Icon, tint, label, value, foot }) => (
  <div className="card overflow-hidden">
    <div className="p-4"><div className="flex items-center gap-2 text-sm text-slate-600"><span className={`grid h-7 w-7 place-items-center rounded-lg ${tint}`}><Icon size={15} /></span>{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight">{value}</div></div>
    <div className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500">{foot}</div>
  </div>
);

export default function Dashboard({ user, open, goAgent }) {
  const [d, setD] = useState(null); const [alerts, setAlerts] = useState([]);
  useEffect(() => { api("/dashboard/").then(setD); api("/alerts/").then(setAlerts); }, []);
  if (!d) return <p>Loading…</p>;
  const pct = d.expected_total ? Math.round((d.recovered_total / d.expected_total) * 100) : 0;
  const entries = Object.entries(d.by_status); const max = Math.max(1, ...entries.map((e) => e[1]));
  const top = Math.max(...entries.map((e) => e[1]));
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">{user.role === "manager" ? "Recovery overview" : "My assigned cases"}</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={FolderOpen} tint="bg-teal-100 text-teal-700" label="Total cases" value={d.total_cases} foot={`${d.new_cases} new · ${d.under_investigation} under investigation`} />
        <Stat icon={Wallet} tint="bg-sky-100 text-sky-700" label="Expected recovery" value={inr(d.expected_total)} foot={`${inr(d.remaining_total)} still to recover`} />
        <Stat icon={TrendingUp} tint="bg-emerald-100 text-emerald-700" label="Recovered" value={inr(d.recovered_total)} foot={`${pct}% of expected · ${d.completed_cases} cases completed`} />
        <Stat icon={AlertTriangle} tint="bg-red-100 text-red-700" label="Delayed cases" value={d.delayed_cases} foot={`${d.awaiting_response} awaiting response`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <div className="font-semibold">Cases by stage</div><div className="mb-3 text-xs text-slate-500">Where every recovery case is right now</div>
          <div className="flex h-44 items-end gap-3">
            {entries.map(([s, n]) => (
              <div key={s} className="flex flex-1 flex-col items-center justify-end gap-1" title={s}>
                <span className="text-xs font-medium text-slate-600">{n}</span>
                <div className={`w-full rounded-t-lg ${n === top && n > 0 ? "bg-gradient-to-t from-teal-100 to-teal-600" : "bg-gradient-to-t from-slate-50 to-slate-200"}`} style={{ height: `${(n / max) * 100}%`, minHeight: 6 }} />
                <span className="w-full truncate text-center text-[11px] text-slate-500">{s.split(" ")[0]}</span>
              </div>))}
          </div>
        </div>
        <div className="card p-4">
          <div className="font-semibold">Recovery progress</div>
          <div className="mt-3 text-4xl font-semibold text-teal-600">{pct}%</div>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-teal-600" style={{ width: pct + "%" }} /></div>
          <div className="mt-2 text-xs text-slate-500">{inr(d.recovered_total)} of {inr(d.expected_total)}</div>
          <button className="btn mt-5 w-full" onClick={goAgent}>Run AI agent on delayed cases</button>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 font-semibold">Needs attention ({alerts.length})</h2>
          <div className="space-y-2">
            {alerts.length === 0 && <p className="card p-4 text-sm text-slate-500">No delays or overdue follow-ups.</p>}
            {alerts.slice(0, 6).map((a) => (
              <button key={a.id} onClick={() => open(a.id)} className="card block w-full p-3 text-left hover:border-teal-600">
                <div className="flex flex-wrap items-center gap-2"><b>{a.recovery_id}</b><span className="text-sm text-slate-500">{a.policyholder} · {a.status}</span>
                  <span className={`chip ${levelClass(a.level)}`}>{a.level}</span>{a.assigned_to && <span className="ml-auto text-xs text-slate-400">{a.assigned_to}</span>}</div>
                <div className="mt-1 text-sm text-slate-600">{a.reasons.join(" · ")}</div>
              </button>))}
          </div>
        </section>
        {user.role === "manager" && (
          <section className="card p-4"><h2 className="font-semibold">Team performance</h2>
            <div className="mt-3 space-y-4">{d.employees.map((e) => { const p = e.expected ? Math.round((e.recovered / e.expected) * 100) : 0; return (
              <div key={e.employee}><div className="flex justify-between text-sm"><b>{e.employee}</b><span className="text-slate-500">{e.total} cases · {e.delayed} delayed</span></div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-teal-600" style={{ width: p + "%" }} /></div>
                <div className="mt-0.5 text-xs text-slate-500">{inr(e.recovered)} of {inr(e.expected)} ({p}%)</div></div>); })}</div>
          </section>)}
      </div>
      <section>
        <h2 className="mb-2 font-semibold">Recent client uploads</h2>
        <div className="grid gap-2 md:grid-cols-2">
          {d.client_uploads.length === 0 && <p className="card p-4 text-sm text-slate-500">No documents uploaded by clients yet.</p>}
          {d.client_uploads.map((u) => (
            <button key={u.id} onClick={() => open(u.case)} className="card p-3 text-left hover:border-teal-600">
              <div className="flex flex-wrap items-center gap-2"><b>{u.recovery_id}</b><span className="text-sm text-slate-500">{u.name} · {u.policyholder}</span>
                <span className={`chip ml-auto ${u.complete ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{u.complete ? "Looks complete" : "Check content"}</span></div>
              {u.summary && <p className="mt-1 line-clamp-2 text-xs text-slate-600">{u.summary}</p>}
            </button>))}
        </div>
      </section>
    </div>
  );
}
