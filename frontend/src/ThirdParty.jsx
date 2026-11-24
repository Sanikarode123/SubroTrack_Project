import React, { useEffect, useState } from "react";
import { api, inr, fmtDate } from "./api.js";

const EVENTS = [["request_sent", "Recovery request sent"], ["acknowledged", "Acknowledged by insurer"], ["query", "Query / more information requested"],
  ["info_sent", "Information sent to insurer"], ["offer", "Settlement offer received"], ["partial_payment", "Part payment promised"],
  ["rejected", "Claim rejected / disputed"], ["settled", "Settlement agreed"]];
const tone = { rejected: "bg-red-100 text-red-800", settled: "bg-emerald-100 text-emerald-800", offer: "bg-sky-100 text-sky-800", partial_payment: "bg-sky-100 text-sky-800", query: "bg-amber-100 text-amber-900" };

const Money = ({ items }) => (
  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
    {items.map(([l, v]) => <div key={l} className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-lg font-semibold">{inr(v)}</div></div>)}
  </div>
);

// Per-case tab: everything the third-party insurer has said or done, plus the money position
export function CaseThirdParty({ c, reload, canEdit }) {
  const blank = { event_type: "request_sent", party: c.third_party || "", reference_no: "", amount: "", note: "", event_date: new Date().toISOString().slice(0, 10), next_followup_date: "" };
  const [f, setF] = useState(blank); const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault(); setErr("");
    try { await api(`/cases/${c.id}/third-party/`, { method: "POST", body: f }); setF(blank); reload(); } catch (x) { setErr(x.message); }
  };
  const evs = c.third_party_events || [];
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-2 p-4 text-sm">
        <span className="text-slate-500">Insurer / party:</span><b>{c.third_party || "—"}</b>
        <span className="ml-3 text-slate-500">Current stage:</span>
        <span className={`chip ${tone[evs[0]?.event_type] || "bg-slate-100 text-slate-700"}`}>{evs[0] ? evs[0].event_label : "Request not sent yet"}</span>
      </div>
      <Money items={[["Paid by our insurer", c.amount_paid], ["Expected recovery", c.expected_recovery], ["Recovered so far", c.amount_recovered], ["Still to recover", c.remaining_amount]]} />
      {canEdit && (
        <form onSubmit={save} className="card grid gap-3 p-4 md:grid-cols-3">
          <div><label className="label">Response / step</label><select className="input" value={f.event_type} onChange={set("event_type")}>{EVENTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
          <div><label className="label">Insurer / party</label><input className="input" value={f.party} onChange={set("party")} /></div>
          <div><label className="label">Their reference no.</label><input className="input" value={f.reference_no} onChange={set("reference_no")} /></div>
          <div><label className="label">Amount offered / promised (₹)</label><input className="input" type="number" step="0.01" value={f.amount} onChange={set("amount")} /></div>
          <div><label className="label">Date</label><input className="input" type="date" value={f.event_date} onChange={set("event_date")} /></div>
          <div><label className="label">Next follow-up</label><input className="input" type="date" value={f.next_followup_date} onChange={set("next_followup_date")} /></div>
          <div className="md:col-span-3"><label className="label">What did they say?</label><input className="input" value={f.note} onChange={set("note")} /></div>
          {err && <p className="text-sm text-red-700 md:col-span-3">{err}</p>}
          <div className="md:col-span-3"><button className="btn">Record response</button></div>
        </form>)}
      <ol className="card divide-y divide-slate-100">
        {evs.length === 0 && <li className="p-4 text-sm text-slate-500">No communication with the third party recorded yet.</li>}
        {evs.map((e) => (
          <li key={e.id} className="p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2"><span className={`chip ${tone[e.event_type] || "bg-slate-100 text-slate-700"}`}>{e.event_label}</span>
              <span className="text-xs text-slate-500">{fmtDate(e.event_date)}{e.reference_no && ` · Ref ${e.reference_no}`}{e.created_by_name && ` · ${e.created_by_name}`}</span>
              {e.amount && <b className="ml-auto">{inr(e.amount)}</b>}</div>
            {e.note && <p className="mt-1 text-slate-700">{e.note}</p>}
          </li>))}
      </ol>
      {c.payments?.length > 0 && (
        <div><h3 className="mb-1 text-sm font-semibold">Payments received</h3>
          <div className="card divide-y divide-slate-100">{c.payments.map((p) => <div key={p.id} className="flex justify-between p-3 text-sm"><span>{fmtDate(p.date)} · {p.paid_by || "Third party"}{p.note && ` · ${p.note}`}</span><b>{inr(p.amount)}</b></div>)}</div></div>)}
    </div>
  );
}

// Staff page: insurer-wise tracking
export default function ThirdParties({ open }) {
  const [d, setD] = useState(null); const [sel, setSel] = useState(null);
  useEffect(() => { api("/third-parties/").then(setD); }, []);
  if (!d) return <p>Loading…</p>;
  const cur = d.parties.find((p) => p.party === sel);
  return (
    <div className="space-y-5">
      <div><h1 className="text-xl font-semibold">Third-party insurers</h1><p className="text-sm text-slate-500">How each insurer or responsible party is responding, and how much has been paid against what was claimed.</p></div>
      <Money items={[["Paid out by us", d.totals.paid_by_us], ["Claimed from third parties", d.totals.claimed], ["Recovered", d.totals.recovered], ["Outstanding", d.totals.outstanding]]} />
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm"><thead className="bg-slate-50 text-left text-slate-500"><tr>
          {["Insurer / party", "Cases", "Claimed", "Recovered", "Outstanding", "Awaiting reply", "Last response"].map((h) => <th key={h} className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {d.parties.length === 0 && <tr><td colSpan="7" className="px-3 py-8 text-center text-slate-500">No third parties yet.</td></tr>}
            {d.parties.map((p) => (
              <tr key={p.party} onClick={() => setSel(sel === p.party ? null : p.party)} className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${sel === p.party ? "bg-teal-50" : ""}`}>
                <td className="px-3 py-2.5 font-medium">{p.party}</td><td className="px-3">{p.cases.length}</td><td className="px-3">{inr(p.claimed)}</td>
                <td className="px-3">{inr(p.recovered)}</td><td className="px-3 font-medium">{inr(p.outstanding)}</td>
                <td className={`px-3 ${p.awaiting ? "font-semibold text-amber-700" : ""}`}>{p.awaiting}</td><td className="px-3">{fmtDate(p.last_response)}</td></tr>))}
          </tbody></table>
      </div>
      {cur && (
        <div className="card p-4"><h2 className="mb-2 font-semibold">{cur.party}: case-wise progress</h2>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-slate-500"><tr>
            {["Case", "Insurer's latest step", "Last update", "Offer", "Claimed", "Recovered", "Remaining"].map((h) => <th key={h} className="py-2 pr-3 font-medium">{h}</th>)}</tr></thead>
            <tbody>{cur.cases.map((c) => (
              <tr key={c.id} onClick={() => open(c.id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                <td className="py-2 pr-3"><b>{c.recovery_id}</b><div className="text-xs text-slate-500">{c.policyholder}</div></td><td className="pr-3">{c.stage}</td><td className="pr-3">{fmtDate(c.last_update)}</td>
                <td className="pr-3">{c.offer ? inr(c.offer) : "—"}</td><td className="pr-3">{inr(c.claimed)}</td><td className="pr-3">{inr(c.recovered)}</td><td className="pr-3">{inr(c.remaining)}</td></tr>))}</tbody></table></div>
        </div>)}
    </div>
  );
}
