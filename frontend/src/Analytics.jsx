import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, Loader2, Database } from "lucide-react";
import { api, inr, fmtDate } from "./api.js";

const pct = (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`);
const days = (v) => (v == null ? "—" : `${Number(v).toFixed(1)} d`);
const num = (v) => Number(v || 0).toLocaleString("en-IN");

const Panel = ({ n, title, sub, children }) => (
  <section className="card p-4">
    <div className="mb-3"><div className="font-semibold"><span className="mr-2 text-teal-600">{n}</span>{title}</div><div className="text-xs text-slate-500">{sub}</div></div>
    {children}
  </section>
);

const Empty = () => <p className="text-sm text-slate-500">No data for this analysis yet.</p>;

function Bars({ rows, label, value, format, tone = "bg-teal-600" }) {
  const max = Math.max(1, ...rows.map((r) => Number(r[value] || 0)));
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r[label]}>
          <div className="flex justify-between text-xs"><span className="truncate pr-2">{r[label]}</span><span className="font-medium">{format(r[value])}</span></div>
          <div className="mt-0.5 h-2.5 rounded-full bg-slate-100"><div className={`h-full rounded-full ${tone}`} style={{ width: `${(Number(r[value] || 0) / max) * 100}%` }} /></div>
        </div>))}
    </div>
  );
}

function Table({ cols, rows, keyOf }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-500"><tr>{cols.map(([h]) => <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => <tr key={r[keyOf]} className="border-t border-slate-100">{cols.map(([h, k, f]) => <td key={h} className="whitespace-nowrap px-3 py-2">{f ? f(r[k]) : r[k]}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Trend({ data }) {
  const W = 600, H = 190, P = 30, max = Math.max(1, ...data.map((d) => d.recovered));
  const x = (i) => P + (data.length === 1 ? 0.5 : i / (data.length - 1)) * (W - 2 * P);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const line = (k) => data.map((d, i) => `${x(i)},${y(d[k])}`).join(" ");
  const step = Math.ceil(data.length / 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <polyline points={`${x(0)},${H - P} ${line("recovered")} ${x(data.length - 1)},${H - P}`} className="fill-teal-100/70 stroke-none" />
      <polyline points={line("recovered")} fill="none" className="stroke-teal-600" strokeWidth="2.5" />
      <polyline points={line("moving_avg")} fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4 3" />
      {data.map((d, i) => <circle key={d.month} cx={x(i)} cy={y(d.recovered)} r="3.5" className="fill-teal-600"><title>{d.month}: {inr(d.recovered)}</title></circle>)}
      {data.map((d, i) => i % step === 0 && <text key={d.month} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="#64748b">{d.month}</text>)}
    </svg>
  );
}

const trendTone = { Rising: "bg-emerald-100 text-emerald-800", Falling: "bg-red-100 text-red-800", Stable: "bg-sky-100 text-sky-800" };

export default function Analytics() {
  const [st, setSt] = useState(null); const [res, setRes] = useState(null); const [err, setErr] = useState("");
  const wasRunning = useRef(false);
  const loadStatus = () => api("/analytics/status/").then((s) => { setSt(s); return s; });
  const loadResults = () => api("/analytics/results/").then((r) => setRes(r.meta ? r : null));
  const refresh = async (force = false) => {
    setErr("");
    try { setSt(await api("/analytics/refresh/", { method: "POST", body: { force } })); } catch (e) { setErr(e.message); }
  };
  const stop = () => api("/analytics/cancel/", { method: "POST" }).then(setSt).catch((e) => setErr(e.message));
  useEffect(() => {
    let alive = true;
    loadResults();
    refresh(false); // Spark runs only when this page is opened, and only if the case data changed since the last run
    const t = setInterval(async () => { // while the page stays open: collect finished runs and react to data changes
      const s = await loadStatus().catch(() => null);
      if (!alive || !s) return;
      if (s.state === "running") { wasRunning.current = true; return; }
      if (wasRunning.current) { wasRunning.current = false; loadResults(); return; }
      if (s.stale && s.state !== "failed") refresh(false);
    }, 4000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  useEffect(() => { if (st?.state === "running") wasRunning.current = true; }, [st?.state]);
  const running = st?.state === "running";
  const m = res?.meta;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="mr-auto"><h1 className="text-xl font-semibold">Spark Analytics</h1>
          <p className="text-sm text-slate-500">Large-scale analysis of recovery data, processed with Apache Spark (PySpark). It updates automatically when your case data changes while this page is open.</p></div>
        <div className="flex gap-2">
          {running && <button className="btn-ghost" onClick={stop}>Stop</button>}
          <button className="btn" disabled={running} onClick={() => refresh(true)}>{running ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}{running ? (st.stage || "Updating…") : "Refresh now"}</button>
        </div>
      </div>
      {err && <p className="card border-red-200 p-3 text-sm text-red-700">{err}</p>}
      {st?.state === "failed" && <p className="card whitespace-pre-wrap border-red-200 p-3 text-xs text-red-700">The last run failed: {st.message}{"\n\n"}To diagnose, run in the backend folder: python manage.py check_spark</p>}

      <div className="card flex flex-wrap items-center gap-x-5 gap-y-1 p-3 text-xs text-slate-600">
        <span className="flex items-center gap-1.5"><Database size={14} className="text-teal-600" /><b>{running ? (st.stage || "Running") : st?.state === "succeeded" ? "Last run succeeded" : "No successful run yet"}</b></span>
        {st?.worker_alive && <span className="chip bg-emerald-100 text-emerald-800">Warm Spark worker: re-runs are fast</span>}
        {m && <>
          <span>Generated {new Date(m.generated_at).toLocaleString("en-IN")}</span><span>Took {m.duration_s}s</span>
          <span>Spark {m.spark_version}</span><span>Source: {m.source === "jdbc" ? "PostgreSQL (JDBC)" : "database export"}</span>
          <span>{num(m.cases)} cases · {num(m.payments)} payments · {num(m.activities)} activities</span>
          <span>{m.parquet_ok ? "Saved to Parquet" : "Parquet not saved (check Hadoop/winutils)"}</span></>}
      </div>

      {running && !st.worker_alive && <p className="text-xs text-slate-500">The first run starts the Spark engine (20 to 60 seconds). It then stays warm, so later runs take only a few seconds.</p>}
      {!res && !running && <p className="card p-8 text-center text-sm text-slate-500">Analytics start automatically when you open this page. If nothing appears, use <b>Refresh now</b>.</p>}

      {res && <>
        {res.insights.length > 0 && <div className="card bg-teal-50 p-4"><div className="mb-1 text-sm font-semibold text-teal-900">Key findings</div>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-teal-900">{res.insights.map((i) => <li key={i}>{i}</li>)}</ul></div>}

        <Panel n="1" title="Employee-wise recovery" sub="Cases handled and amount recovered by each employee">
          {res.employee.length === 0 ? <Empty /> : <div className="grid gap-4 lg:grid-cols-2">
            <div><div className="mb-2 text-xs font-medium text-slate-500">Amount recovered</div><Bars rows={res.employee} label="employee" value="recovered_total" format={inr} /></div>
            <div><div className="mb-2 text-xs font-medium text-slate-500">Cases handled</div><Bars rows={res.employee} label="employee" value="cases_handled" format={num} tone="bg-sky-500" /></div>
            <div className="lg:col-span-2"><Table keyOf="employee" rows={res.employee} cols={[["Employee", "employee"], ["Cases", "cases_handled"], ["Completed", "closed_cases"], ["Expected", "expected_total", inr], ["Recovered", "recovered_total", inr], ["Recovery rate", "recovery_rate", pct], ["Avg case amount", "avg_case_amount", inr]]} /></div></div>}
        </Panel>

        <Panel n="2" title="Monthly recovery trend" sub="Total amount recovered each month, with a 3-month moving average (dashed)">
          {res.monthly.length === 0 ? <Empty /> : <>
            <div className="mb-2"><span className={`chip ${trendTone[res.monthly_trend] || "bg-slate-100 text-slate-600"}`}>Trend: {res.monthly_trend}</span></div>
            <Trend data={res.monthly} />
            <div className="mt-3"><Table keyOf="month" rows={[...res.monthly].reverse()} cols={[["Month", "month"], ["Recovered", "recovered", inr], ["Payments", "payments"], ["Change vs previous", "mom_change", pct], ["3-month average", "moving_avg", inr]]} /></div></>}
        </Panel>

        <Panel n="3" title="Case status analysis" sub="Where cases sit in the recovery workflow">
          <div className="grid gap-4 lg:grid-cols-2">
            <Bars rows={res.status} label="status" value="cases" format={num} />
            <Table keyOf="status" rows={res.status} cols={[["Status", "status"], ["Cases", "cases"], ["Share", "share", pct], ["Expected", "expected", inr], ["Recovered", "recovered", inr]]} />
          </div>
        </Panel>

        <Panel n="4" title="Recovery performance" sub="Average recovery and time to recover, by claim size and by insurer. Days are counted from case creation.">
          <div className="space-y-4">
            {[["By claim size", res.performance.amount_band], ["By third-party insurer", res.performance.third_party]].map(([t, rows]) => (
              <div key={t}><div className="mb-1 text-sm font-medium">{t}</div>
                <Table keyOf="segment" rows={rows} cols={[["Type", "segment"], ["Cases", "cases"], ["Avg recovered per paying case", "avg_recovered", inr], ["Recovery rate", "recovery_rate", pct], ["Days to first payment", "avg_days_first", days], ["Days to full recovery", "avg_days_full", days]]} /></div>))}
          </div>
        </Panel>

        <Panel n="5" title="Delayed case analytics" sub={`A case counts as delayed when it went ${res.delays.threshold_days}+ days without any activity at some point in its history`}>
          <div className="grid gap-4 lg:grid-cols-2">
            <div><div className="mb-2 text-xs font-medium text-slate-500">Delayed share by insurer</div>
              <Bars rows={res.delays.by_third_party} label="segment" value="delayed_pct" format={pct} tone="bg-amber-500" /></div>
            <div><div className="mb-2 text-xs font-medium text-slate-500">Delayed share by claim size</div>
              <Bars rows={res.delays.by_amount_band} label="segment" value="delayed_pct" format={pct} tone="bg-amber-500" /></div>
            <div className="lg:col-span-2"><Table keyOf="segment" rows={[...res.delays.by_third_party, ...res.delays.by_amount_band]}
              cols={[["Type", "segment"], ["Cases", "cases"], ["Delayed", "delayed_cases"], ["Delayed %", "delayed_pct", pct], ["Avg longest gap", "avg_longest_gap", days], ["Days to full recovery", "avg_days_full", days]]} /></div>
            {res.delays.by_status.length > 0 && <div className="lg:col-span-2"><div className="mb-2 text-xs font-medium text-slate-500">Where delayed cases are stuck</div>
              <Bars rows={res.delays.by_status} label="status" value="delayed_cases" format={num} tone="bg-red-500" /></div>}
          </div>
        </Panel>
      </>}
    </div>
  );
}
