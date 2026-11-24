const BASE = import.meta.env.VITE_API_URL || "/api";
export const STATUSES = ["New Case", "Under Investigation", "Recovery Initiated", "Awaiting Response",
  "Negotiation / Follow-up", "Recovered / Partially Recovered", "Closed"];

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = localStorage.getItem("token");
  if (token) headers.Authorization = `Token ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(BASE + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  if (res.status === 401) { localStorage.removeItem("token"); window.location.reload(); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(Object.values(data).flat().join(" ") || "Request failed");
  return data;
}

export const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
export const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—");

const tone = { Overdue: "bg-red-100 text-red-800", "Needs Attention": "bg-amber-100 text-amber-900", Upcoming: "bg-sky-100 text-sky-800", OK: "bg-emerald-100 text-emerald-800" };
export const levelClass = (l) => tone[l] || tone.OK;
