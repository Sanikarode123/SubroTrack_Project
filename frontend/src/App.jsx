import React, { useEffect, useState } from "react";
import { LayoutDashboard, FolderOpen, Bot, Building2, Users, BarChart3, FileSearch, Search, LogOut } from "lucide-react";
import { api } from "./api.js";
import Dashboard from "./Dashboard.jsx";
import Cases from "./Cases.jsx";
import CaseDetail from "./CaseDetail.jsx";
import Agent from "./Agent.jsx";
import ThirdParties from "./ThirdParty.jsx";
import People from "./People.jsx";
import Analytics from "./Analytics.jsx";
import RagSearch from "./RagSearch.jsx";
import { ClientHome, ClientCase } from "./ClientPortal.jsx";

const ROLES = [["manager", "Manager"], ["employee", "Employee"], ["client", "Client"]];
const NAV = {
  manager: [["dashboard", "Dashboard", LayoutDashboard], ["cases", "Cases", FolderOpen], ["thirdparty", "Third parties", Building2], ["agent", "AI Agent", Bot], ["rag", "Evidence search", FileSearch], ["analytics", "Data Analytics", BarChart3], ["people", "People", Users]],
  employee: [["dashboard", "My work", LayoutDashboard], ["cases", "My cases", FolderOpen], ["thirdparty", "Third parties", Building2], ["agent", "AI Agent", Bot], ["rag", "Evidence search", FileSearch]],
  client: [["home", "My claims", FolderOpen]],
};
const WORKSPACE = { manager: "Manager workspace", employee: "Employee workspace", client: "Client portal" };

function Login({ onDone }) {
  const [role, setRole] = useState("manager");
  const [f, setF] = useState({ username: "", password: "" });
  const [err, setErr] = useState("");
  useEffect(() => { document.documentElement.dataset.theme = role; }, [role]);
  const submit = async (e) => {
    e.preventDefault(); setErr("");
    const r = await fetch((import.meta.env.VITE_API_URL || "/api") + "/login/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...f, role }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return setErr(d.detail || "Could not sign in.");
    localStorage.setItem("token", d.token); onDone();
  };
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-7">
        <div><h1 className="text-2xl font-bold tracking-tight">SubroTrack</h1><p className="text-sm text-slate-500">Subrogation recovery tracking</p></div>
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1">
          {ROLES.map(([k, l]) => <button type="button" key={k} onClick={() => setRole(k)} className={`rounded-lg py-1.5 text-sm ${role === k ? "bg-white font-semibold text-teal-700 shadow-sm" : "text-slate-500"}`}>{l}</button>)}
        </div>
        <div><label className="label" htmlFor="u">Username</label><input id="u" className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoFocus /></div>
        <div><label className="label" htmlFor="p">Password</label><input id="p" type="password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
        {err && <p className="text-sm text-red-700">{err}</p>}
        <button className="btn w-full">Sign in as {role}</button>
      </form>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState(null);
  const [q, setQ] = useState("");
  const load = () => api("/me/").then((u) => { setUser(u); setView({ page: u.role === "client" ? "home" : "dashboard" }); }).catch(() => setUser(null));
  useEffect(() => { if (localStorage.getItem("token")) load(); }, []);
  useEffect(() => { if (user) document.documentElement.dataset.theme = user.role; }, [user]);
  if (!user || !view) return <Login onDone={load} />;
  const open = (id) => setView({ page: user.role === "client" ? "ccase" : "case", id });
  const go = (page) => setView({ page });
  const crumb = { dashboard: "Overview", cases: "All cases", case: "Case detail", agent: "Delay monitor", thirdparty: "Third parties", people: "People", analytics: "Spark Analytics", rag: "Evidence search", home: "My claims", ccase: "Claim detail" }[view.page];
  const staff = user.role !== "client";
  return (
    <div className="min-h-screen gap-4 p-3 md:flex">
      <aside className="card flex shrink-0 flex-col md:sticky md:top-3 md:h-[calc(100vh-1.5rem)] md:w-60">
        <div className="px-5 py-5"><div className="text-xl font-bold tracking-tight">SubroTrack</div><div className="text-xs text-slate-400">{WORKSPACE[user.role]}</div></div>
        <nav className="flex gap-1 overflow-x-auto px-3 md:flex-col">
          {NAV[user.role].map(([k, l, Icon]) => {
            const on = view.page === k || (k === "cases" && view.page === "case") || (k === "home" && view.page === "ccase");
            return <button key={k} onClick={() => go(k)} className={`flex items-center gap-2.5 whitespace-nowrap rounded-xl px-3 py-2.5 text-left text-sm ${on ? "border border-slate-200 bg-white font-semibold text-teal-700 shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}><Icon size={16} />{l}</button>;
          })}
        </nav>
        <div className="mt-auto hidden space-y-3 p-4 md:block">
          <div className="rounded-xl bg-teal-50 p-3 text-xs text-teal-900">Signed in as <b>{user.name}</b><br /><span className="capitalize">{user.role}</span></div>
          <button className="flex items-center gap-2 text-sm text-slate-600 hover:text-ink" onClick={() => { localStorage.removeItem("token"); setUser(null); setView(null); }}><LogOut size={15} />Sign out</button>
        </div>
      </aside>
      <main className="card min-w-0 flex-1 p-4 md:p-6">
        <header className="mb-5 flex items-center gap-3">
          <div className="text-sm text-slate-500">{WORKSPACE[user.role]} <span className="mx-1">›</span><span className="font-medium text-teal-600">{crumb}</span></div>
          {staff && (
            <form className="relative ml-auto w-full max-w-xs" onSubmit={(e) => { e.preventDefault(); setView({ page: "cases", q }); }}>
              <Search size={14} className="absolute left-3 top-3 text-slate-400" />
              <input className="input rounded-full pl-8" placeholder="Search cases" value={q} onChange={(e) => setQ(e.target.value)} /></form>)}
          <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-full bg-teal-100 text-sm font-semibold text-teal-700 ${staff ? "" : "ml-auto"}`}>{user.name[0].toUpperCase()}</div>
        </header>
        {view.page === "dashboard" && <Dashboard user={user} open={open} goAgent={() => go("agent")} />}
        {view.page === "cases" && <Cases key={view.q || "all"} initialQ={view.q || ""} open={open} user={user} />}
        {view.page === "case" && <CaseDetail id={view.id} user={user} back={() => go("cases")} />}
        {view.page === "thirdparty" && <ThirdParties open={open} />}
        {view.page === "agent" && <Agent open={open} />}
        {view.page === "people" && <People />}
        {view.page === "analytics" && <Analytics />}
        {view.page === "rag" && <RagSearch open={open} />}
        {view.page === "home" && <ClientHome user={user} open={open} />}
        {view.page === "ccase" && <ClientCase id={view.id} back={() => go("home")} />}
      </main>
    </div>
  );
}
