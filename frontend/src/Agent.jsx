import React, { useEffect, useState } from "react";
import { Bot, CheckCircle2, Wrench } from "lucide-react";
import { api, inr } from "./api.js";

const DEFAULT = "Check all pending recovery cases and tell me which cases need attention.";
const PR = { High: "bg-red-100 text-red-800", Medium: "bg-amber-100 text-amber-900", Low: "bg-sky-100 text-sky-800" };
const ST = { accepted: "Accepted", done: "Done", snoozed: "Snoozed", dismissed: "Dismissed", superseded: "Replaced by newer run" };

function Finding({ f, open, onChange }) {
  const [mode, setMode] = useState(null); const [note, setNote] = useState(""); const [date, setDate] = useState(""); const [err, setErr] = useState("");
  const send = async (action) => {
    setErr("");
    try { onChange(await api(`/agent/findings/${f.id}/respond/`, { method: "POST", body: { action, note, next_followup_date: date || null } })); setMode(null); }
    catch (e) { setErr(e.message); }
  };
  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`chip ${PR[f.priority]}`}>{f.priority} priority</span>
        <button className="font-semibold text-teal-700 hover:underline" onClick={() => open(f.case)}>{f.recovery_id}</button>
        <span className="text-sm text-slate-500">{f.policyholder} · {f.case_status}</span>
        <span className="ml-auto chip bg-slate-100 text-slate-500">{f.source === "ollama" ? "Qwen3" : "rule-based"}</span>
      </div>
      <p className="mt-2 text-sm"><b>Why:</b> {f.reason}</p>
      <ul className="mt-1 list-disc pl-5 text-xs text-slate-500">{f.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <p className="mt-2 rounded-lg bg-teal-50 p-2.5 text-sm text-teal-900"><b>Suggested next action:</b> {f.suggested_action}</p>
      {f.status !== "open" ? (
        <p className="mt-3 flex items-center gap-1.5 text-sm text-slate-600"><CheckCircle2 size={15} className="text-emerald-600" /><b>{ST[f.status]}</b>{f.employee_note && <span>— {f.employee_note}</span>}</p>
      ) : (
        <div className="mt-3 space-y-2">
          {!mode ? (
            <div className="flex flex-wrap gap-2">
              <button className="btn" onClick={() => send("accept")}>I'll do this</button>
              <button className="btn-ghost" onClick={() => setMode("done")}>Mark done</button>
              <button className="btn-ghost" onClick={() => setMode("snooze")}>Snooze</button>
              <button className="btn-ghost" onClick={() => setMode("dismiss")}>Dismiss</button>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              {mode === "snooze" && <div><label className="label">Remind me on</label><input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} /></div>}
              <div className="min-w-[14rem] flex-1"><label className="label">{mode === "done" ? "What did you do?" : mode === "dismiss" ? "Why dismiss?" : "Note (optional)"}</label>
                <input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></div>
              <button className="btn" onClick={() => send(mode)}>Save response</button><button className="btn-ghost" onClick={() => setMode(null)}>Cancel</button>
            </div>)}
          {err && <p className="text-sm text-red-700">{err}</p>}
        </div>)}
    </div>
  );
}

export default function Agent({ open }) {
  const [run, setRun] = useState(null); const [busy, setBusy] = useState(false); const [instr, setInstr] = useState(DEFAULT); const [show, setShow] = useState("open");
  useEffect(() => { api("/agent/latest/").then((r) => setRun(r && r.id ? r : null)); }, []);
  const go = async () => { setBusy(true); try { setRun(await api("/agent/run/", { method: "POST", body: { instruction: instr } })); setShow("open"); } finally { setBusy(false); } };
  const update = (nf) => setRun({ ...run, findings: run.findings.map((f) => (f.id === nf.id ? nf : f)) });
  const list = run ? run.findings.filter((f) => (show === "open" ? f.status === "open" : f.status !== "open")) : [];
  return (
    <div className="space-y-5">
      <div><h1 className="flex items-center gap-2 text-xl font-semibold"><Bot size={20} className="text-teal-600" />Delayed-case AI agent</h1>
        <p className="text-sm text-slate-500">The agent checks every open case with its monitoring tools, ranks them, explains why each needs attention and suggests the next step. You decide what to do with each suggestion.</p></div>
      <div className="card flex flex-wrap items-end gap-2 p-4">
        <div className="min-w-[16rem] flex-1"><label className="label">Ask the agent</label><input className="input" value={instr} onChange={(e) => setInstr(e.target.value)} /></div>
        <button className="btn" disabled={busy} onClick={go}>{busy ? "Agent is working…" : "Run agent"}</button>
      </div>
      {busy && <p className="text-sm text-slate-500">Checking cases and writing explanations. The first AI call can take up to a minute while the model loads.</p>}
      {run && (<>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="card p-4 lg:col-span-2"><div className="mb-1 font-semibold">Briefing</div><p className="whitespace-pre-wrap text-sm text-slate-700">{run.summary}</p>
            <p className="mt-2 text-xs text-slate-400">Request: “{run.instruction}” · {new Date(run.created_at).toLocaleString("en-IN")}</p></div>
          
        </div>
        <div className="flex gap-1 border-b border-slate-200 text-sm">
          {[["open", `To review (${run.findings.filter((f) => f.status === "open").length})`], ["done", "Responded"]].map(([k, l]) => (
            <button key={k} onClick={() => setShow(k)} className={`px-3 py-2 ${show === k ? "border-b-2 border-teal-600 font-semibold" : "text-slate-500"}`}>{l}</button>))}
        </div>
        <div className="space-y-3">
          {list.length === 0 && <p className="card p-4 text-sm text-slate-500">{show === "open" ? "Nothing left to review." : "No responses recorded yet."}</p>}
          {list.map((f) => <Finding key={f.id} f={f} open={open} onChange={update} />)}
        </div>
      </>)}
      {!run && !busy && <p className="card p-6 text-center text-sm text-slate-500">No report yet. Click <b>Run agent</b> to scan your open cases.</p>}
    </div>
  );
}
