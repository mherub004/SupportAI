"use client";
import { useCallback, useEffect, useState } from "react";
import Icon from "./Icon";
import { workspaceHeaders } from "../../lib/workspace-client";
type Handoff = { message_id: string; thread_id: string; subject: string; sender: string; recipient: string; reasons: string[]; active: boolean; status: string; error: string };
const notificationLabels: Record<string, string> = { pending: "Notification queued", reserved: "Checking notification delivery", uncertain: "Delivery needs verification", sent: "Agent notified", failed: "Notification needs attention", resolved: "Handoff completed" };
async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { method, headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, cache: "no-store", body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Handoff request failed"); return data;
}
export default function HumanHandoffs({ open, onChanged }: { open: (id: string) => void; onChanged: () => Promise<void> }) {
  const [items, setItems] = useState<Handoff[]>([]), [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const load = useCallback(async () => setItems(await api<Handoff[]>("handoffs")), []);
  useEffect(() => { void load().catch(e => setError(e.message)); const timer = setInterval(() => void load().catch(e => setError(e.message)), 10000); return () => clearInterval(timer); }, [load]);
  async function action(task: () => Promise<unknown>, text: string) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); await load(); await onChanged(); setNotice(text); }
    catch (e) { setError(e instanceof Error ? e.message : "Handoff failed"); }
    finally { setBusy(false); }
  }
  return <section className="panel"><div className="panel-heading"><div><h2>Conversations for your team</h2><p className="muted">AI replies pause on these threads. Notifications go to the escalation email configured in the business profile.</p></div><span className="badge escalate">{items.filter(h => h.active).length} active</span></div>
    {error && <p className="error alert" role="alert">{error}</p>}{notice && <p className="notice alert" role="status">{notice}</p>}
    {!items.length && <div className="empty"><span className="empty-symbol"><Icon name="handoff"/></span><h3>No conversations waiting for handoff</h3><p>When a request needs a person, it will appear here with its reason and notification status.</p></div>}
    <div className="handoff-list">{items.map(item => <article className="handoff-card" key={item.message_id}><div className="handoff-heading"><span className={`badge ${item.active ? "escalate" : "eligible"}`}>{item.active ? "Human handling" : "Returned to assistant"}</span><span className="muted small">{notificationLabels[item.status] || "Notification needs attention"}</span></div><h3>{item.subject}</h3><p className="muted">{item.sender}</p><div className="reason-tags">{item.reasons.map(reason => <span key={reason}>{reason.replaceAll("_", " ")}</span>)}</div><small>Escalation contact: {item.recipient}</small>{item.error && <p className="error small">{item.status === "uncertain" || item.status === "reserved" ? "Gmail delivery was not confirmed. Verify the existing notification before taking further action." : "The notification could not complete. Check your Google connection and escalation contact, then retry."}</p>}<div className="setup-actions"><button disabled={busy} onClick={() => open(item.message_id)}>Review conversation</button>{item.active && <button disabled={busy} onClick={() => void action(() => api(`threads/${encodeURIComponent(item.thread_id)}/ownership`, "PUT", { paused: false, owner: "assistant" }), "Handoff resolved. The assistant may handle new messages under your reply policy.")}>Resume assistant</button>}{item.active && item.status === "failed" && <button disabled={busy} onClick={() => void action(() => api(`handoffs/${encodeURIComponent(item.message_id)}/retry`, "POST"), "Human notification queued for the current escalation contact.")}>Retry notification</button>}{["reserved", "uncertain"].includes(item.status) && <button disabled={busy} onClick={() => void action(() => api(`handoffs/${encodeURIComponent(item.message_id)}/reconcile`, "POST"), "Existing Gmail notification confirmed. No second alert was sent.")}>Verify Gmail notification</button>}</div></article>)}</div>
  </section>;
}
