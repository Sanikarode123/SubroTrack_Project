
import React, { useEffect, useState } from "react";
import { Upload, Plus } from "lucide-react";
import { api, inr, levelClass, STATUSES } from "./api.js";

export default function Cases({ open, initialQ, user }) {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState(initialQ); const [status, setStatus] = useState("");
  const [show, setShow] = useState(false); const [report, setReport] = useState(null); const [busy, setBusy] = useState(false);
  const load = () => api(`/cases/?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`).then(setRows);
  useEffect(() => { load(); }, [status]);

  const importFile = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const form = new FormData(); form.append("file", file); setBusy(true); setReport(null);
    try { setReport(await api("/cases/import-csv/", { method: "POST", form })); load(); }
    catch (err) { setReport({ error: err.message }); } finally { setBusy(false); }
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Recovery cases</h1>
        {user.role === "manager" && <>
        <label className="btn-ghost cursor-pointer"><Upload size={15} />{busy ? "Reading file…" : "Upload claims file"}<input type="file" accept=".csv,.xlsx,.xlsm" hidden onChange={importFile} /></label>
        <button className="btn" onClick={() => setShow(!show)}><Plus size={15} />Register case</button>
        </>}
      </div>
      {report && (report.error ? <p className="card p-3 text-sm text-red-700">{report.error}</p> : (
        <div className="card space-y-3 p-4">
          <div className="font-semibold">Import result</div>
          <div className="grid grid-cols-2 gap-3 text-center text-sm md:grid-cols-4">
            {[["Rows in file", report.total_rows], ["Subrogation cases added", report.imported], ["Normal claims ignored", report.normal_claims_ignored], ["Duplicates / errors", report.duplicates.length + report.errors.length]].map(([l, v]) => (
              <div key={l} className="rounded-xl bg-slate-50 p-3"><div className="text-2xl font-semibold text-teal-700">{v}</div><div className="text-xs text-slate-500">{l}</div></div>))}
          </div>
          <p className="text-xs text-slate-500">Detected by: {report.mode}</p>
          {report.imported_cases.length > 0 && <p className="text-sm"><b>Added:</b> {report.imported_cases.map((c) => `${c.recovery_id} (${c.policyholder})`).join(", ")}</p>}
          {report.duplicates.length > 0 && <p className="text-sm text-amber-800"><b>Already in SubroTrack:</b> {report.duplicates.join(", ")}</p>}
          {report.errors.length > 0 && <p className="text-sm text-red-700">{report.errors.join(" · ")}</p>}
        </div>))}
      {show && <NewCase done={() => { setShow(false); load(); }} />}
      <form onSubmit={(e) => { e.preventDefault(); load(); }} className="flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder="Search by case ID, claim ID or name" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input max-w-[16rem]" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
        <button className="btn-ghost">Search</button>
      </form>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm"><thead className="bg-slate-50 text-left text-slate-500"><tr>
          {["Case", "Policyholder", "Status", "Owner", "Remaining", "Health"].map((h) => <th key={h} className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan="6" className="px-3 py-8 text-center text-slate-500">No cases found. Register one or upload a claims file.</td></tr>}
            {rows.map((c) => (
              <tr key={c.id} onClick={() => open(c.id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2.5"><b>{c.recovery_id}</b><div className="text-xs text-slate-500">{c.claim_id}</div></td>
                <td className="px-3">{c.policyholder}</td><td className="px-3">{c.status}</td><td className="px-3">{c.assigned_to_name || "—"}</td>
                <td className="px-3">{inr(c.remaining_amount)}</td>
                <td className="px-3"><span className={`chip ${levelClass(c.alert.level)}`}>{c.alert.level}</span></td>
              </tr>))}
          </tbody></table>
      </div>
    </div>
  );
}

function NewCase({ done }) {
  const [f, setF] = useState({ claim_id: "", policyholder: "", third_party: "", amount_paid: "", incident_details: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => { e.preventDefault(); setErr(""); try { await api("/cases/", { method: "POST", body: f }); done(); } catch (x) { setErr(x.message); } };
  return (
    <form onSubmit={submit} className="card grid gap-3 p-4 md:grid-cols-2">
      {[["claim_id", "Original claim ID"], ["policyholder", "Policyholder"], ["third_party", "Third party / insurer"], ["amount_paid", "Amount paid (₹)"]].map(([k, l]) => (
        <div key={k}><label className="label">{l}</label><input className="input" required={k !== "third_party"} value={f[k]} onChange={set(k)} /></div>))}
      <div className="md:col-span-2"><label className="label">Incident details</label><textarea className="input" rows="2" value={f.incident_details} onChange={set("incident_details")} /></div>
      {err && <p className="text-sm text-red-700 md:col-span-2">{err}</p>}
      <div className="md:col-span-2"><button className="btn">Create recovery case</button></div>
    </form>
  );
}
