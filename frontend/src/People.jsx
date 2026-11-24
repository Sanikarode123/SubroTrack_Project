import React, { useEffect, useState } from "react";
import { api } from "./api.js";

export default function People() {
  const [list, setList] = useState([]); const [err, setErr] = useState("");
  const [f, setF] = useState({ name: "", username: "", password: "", role: "employee" });
  const load = () => api("/users/").then(setList);
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const add = async (e) => {
    e.preventDefault(); setErr("");
    try { setList(await api("/users/", { method: "POST", body: f })); setF({ name: "", username: "", password: "", role: f.role }); } catch (x) { setErr(x.message); }
  };
  return (
    <div className="space-y-5">
      <div><h1 className="text-xl font-semibold">People</h1><p className="text-sm text-slate-500">Create logins for employees and clients. Link a client to their claims from the case page.</p></div>
      <form onSubmit={add} className="card grid gap-3 p-4 md:grid-cols-5">
        <div><label className="label">Full name</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">Username</label><input className="input" required value={f.username} onChange={set("username")} /></div>
        <div><label className="label">Password</label><input className="input" type="password" required value={f.password} onChange={set("password")} /></div>
        <div><label className="label">Role</label><select className="input" value={f.role} onChange={set("role")}><option value="employee">Employee</option><option value="client">Client</option></select></div>
        <div className="flex items-end"><button className="btn w-full">Create login</button></div>
        {err && <p className="text-sm text-red-700 md:col-span-5">{err}</p>}
      </form>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm"><thead className="bg-slate-50 text-left text-slate-500"><tr>{["Name", "Username", "Role"].map((h) => <th key={h} className="px-3 py-2.5 font-medium">{h}</th>)}</tr></thead>
          <tbody>{list.map((u) => <tr key={u.id} className="border-t border-slate-100"><td className="px-3 py-2.5">{u.name || "—"}</td><td className="px-3">{u.username}</td><td className="px-3 capitalize">{u.role}</td></tr>)}</tbody></table>
      </div>
    </div>
  );
}
