"use client";
import { workspaceHeaders } from "../lib/workspace-client";
import PersonalSetup from "./components/PersonalSetup";
import CrmContext from "./components/CrmContext";
import BusinessSetup from "./components/BusinessSetup";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type Summary = { id: string; thread_id: string; sender: string; subject: string; status: string; disposition: string; language: string; brand: string; risk_tags: string[]; created_at: string };
type Detail = Summary & { body: string; response: string; model: string; category: string; paused: boolean; owner: string; draft_id: string; provider_version: string; send_state: string | null; citations: { document_id: string; revision: string; quote: string; title: string; url: string }[] };
type Overview = { escalation_email: string; drive_connected: boolean; company_name: string; draft_only: boolean; mode: string; mailbox: string; counts: Record<string, number>; kill_switch: boolean; auto_send_enabled: boolean; documents: number; failed_jobs: number; pending_jobs: number; knowledge_sync: string };
type Knowledge = { id: string; title: string; revision: string; brand: string; model: string; language: string; owner: string; approved: boolean; visibility: string; url: string };
type Event = { id: number; event: string; entity_id: string; actor: string; created_at: string; details: Record<string, unknown> };
type Job = { id: string; kind: string; status: string; attempts: number; error: string };
async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const result = await fetch(`/api/backend/${path}`, { method, headers: { ...workspaceHeaders(), "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store" });
  const data = await result.json();
  if (!result.ok) throw new Error(data.detail || "Request failed");
  return data;
}
const safeLink = (url: string) => { try { return new URL(url).protocol === "https:" ? url : "#"; } catch { return "#"; } };
const stamp = (value: string) => new Date(value + (value.endsWith("Z") ? "" : "Z")).toLocaleString();

export default function Dashboard() {
  const previousFocus = useRef<HTMLElement | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [token, setToken] = useState("");
  const [workspace, setWorkspace] = useState<"company" | "test">("company");
  const [testAvailable, setTestAvailable] = useState(false);
  const [tab, setTab] = useState("Business setup");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [messages, setMessages] = useState<Summary[]>([]);
  const [documents, setDocuments] = useState<Knowledge[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);
  const [response, setResponse] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const refresh = useCallback(async () => {
    const [o, m, d, e, j] = await Promise.all([api<Overview>("overview"), api<Summary[]>("messages"), api<Knowledge[]>("knowledge"), api<Event[]>("audit"), api<Job[]>("jobs")]);
    setOverview(o); setMessages(m); setDocuments(d); setEvents(e); setJobs(j); setAuthenticated(true);
  }, []);
  useEffect(() => {
    fetch("/api/workspace", { headers: workspaceHeaders(), cache: "no-store" }).then(r => r.json()).then(result => {
      setWorkspace(result.workspace); setTestAvailable(result.test_available);
      setTab(result.workspace === "test" ? "Personal setup" : "Business setup");
      return refresh();
    }).catch(() => setAuthenticated(false));
  }, [refresh]);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (["google", "salesforce", "netsuite"].includes(query.get("connection") || "")) {
      setNotice(query.get("result") === "connected" ? "Account connected securely. Verify access and complete your setup." : "Account authorization was not completed. Check provider configuration and selected account, then reconnect.");
      window.history.replaceState({}, "", window.location.pathname + (query.get("workspace") === "test" ? "?workspace=test" : ""));
    }
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    const interval = setInterval(() => refresh().catch(e => setError(e.message)), 10000);
    return () => clearInterval(interval);
  }, [authenticated, refresh]);
  useEffect(() => {
    if (!selected) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = originalOverflow; previousFocus.current?.focus(); };
  }, [selected?.id]);
  const open = async (id: string) => {
    if (!selected) previousFocus.current = document.activeElement as HTMLElement;
    const detail = await api<Detail>(`messages/${encodeURIComponent(id)}`);
    setSelected(detail); setResponse(detail.response); setReason("");
  };
  const action = async (fn: () => Promise<unknown>, success: string, reopen = true) => {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); await refresh(); if (reopen && selected) await open(selected.id); setNotice(success); }
    catch (e) { setError(e instanceof Error ? e.message : "Operation failed"); }
    finally { setBusy(false); }
  };
  const switchWorkspace = async (target: "company" | "test") => {
    setBusy(true); setError("");
    try {
      const result = await fetch("/api/workspace", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspace: target }) });
      const data = await result.json(); if (!result.ok) throw new Error(data.detail || "Cannot switch workspace");
      window.location.assign(target === "test" ? "/?workspace=test" : "/");
    } catch (e) { setError(e instanceof Error ? e.message : "Switch failed"); setBusy(false); }
  };
  const login = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await fetch("/api/session", { method: "POST", headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
      if (!result.ok) throw new Error("Invalid operator token");
      setToken(""); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Sign in failed"); }
    finally { setBusy(false); }
  };
  if (!authenticated) return <main className="login-shell"><div className="login-card"><div className="logo">S<span>f</span></div><p className="eyebrow">SUPPORT OPERATIONS</p><h1>Welcome to<br/>SupportFlow AI.</h1><p>Review grounded replies. Keep people in control.</p><form onSubmit={login}><label htmlFor="token">Operator access token</label><input id="token" type="password" value={token} onChange={e => setToken(e.target.value)} required autoComplete="current-password"/><button disabled={busy} className="primary">{busy ? "Connecting…" : "Open workspace →"}</button></form>{error && <p role="alert" className="error">{error}</p>}<small>Internal pilot · Use the token configured by your administrator.</small></div><div className="login-art"><div className="orbit one"/><div className="orbit two"/><div className="art-copy"><span className="dot"/> KNOWLEDGE → CONFIDENCE<h2>Good support<br/>starts with<br/><em>a trusted source.</em></h2><p>Every response has a source.<br/>Every decision stays accountable.</p></div></div></main>;
  const total = Object.values(overview?.counts || {}).reduce((sum, n) => sum + n, 0);
  const attention = messages.filter(m => m.disposition === "escalate").length;
  return <div className="workspace"><aside><a className="wordmark" href="/">SupportFlow<span>AI</span></a><div className="workspace-switch"><p className="sidebar-label">ENVIRONMENT</p><button className={workspace === "company" ? "nav active" : "nav"} disabled={busy} onClick={() => void switchWorkspace("company")}>Company workspace</button><button className={workspace === "test" ? "nav active" : "nav"} disabled={busy || !testAvailable} onClick={() => void switchWorkspace("test")}>Personal test environment</button></div><p className="sidebar-label">WORKSPACE</p><nav aria-label="Workspace">{(workspace === "test" ? ["Personal setup", "Inbox", "Knowledge", "Activity", "Operations"] : ["Inbox", "Knowledge", "Activity", "Operations", "Business setup"]).map((name, i) => <button key={name} className={tab === name ? "nav active" : "nav"} onClick={() => setTab(name)}><span aria-hidden>{["◇", "▤", "◈", "◷", "⚙", "◇"][i]}</span>{name}{name === "Inbox" && <b>{messages.length}</b>}</button>)}</nav><div className="sidebar-bottom"><span className="tag">{overview?.mode === "demo" ? "SYNTHETIC DEMO" : "LIVE DRAFTS"}</span><p>{overview?.company_name}<br/>{overview?.mailbox}</p><button className="text-button" onClick={async () => { await fetch("/api/session", { method: "DELETE" }); setAuthenticated(false); setSelected(null); }}>Sign out ↗</button></div></aside><main className="main"><header><div><p className="eyebrow">SUPPORT OPERATIONS / {tab.toUpperCase()}</p><h1>{tab === "Personal setup" ? "Try your personal inbox" : tab === "Inbox" ? "Your review workspace" : tab === "Knowledge" ? "Knowledge you can trace" : tab === "Activity" ? "Every decision, recorded" : tab === "Business setup" ? "Set up your business" : "Operational controls"}</h1><p className="muted">{tab === "Inbox" ? "A clear view of conversations that need your attention." : "Approved evidence and human oversight at every step."}</p></div><button onClick={() => action(refresh, "Workspace refreshed", false)} disabled={busy}>↻ Refresh</button></header>{workspace === "test" && <div className="banner"><strong>Personal test environment</strong><span>Separate mailbox, credentials, knowledge and jobs. Company settings stay in the company workspace. Drafts only.</span></div>}{overview?.mode === "setup" && <div className="banner"><strong>Setup in progress</strong><span>Complete your setup to activate draft-only processing.</span></div>}{overview?.mode === "demo" && <div className="banner"><strong>Demo workspace</strong><span>Synthetic customers and documents. No real email is sent.</span></div>}{error && <div role="alert" className="error alert">{error}</div>}{notice && <div role="status" className="notice alert">{notice}</div>}<section className="stats" aria-label="Workspace metrics"><div><span>Conversations</span><strong>{total}</strong><small>In this workspace</small></div><div><span>Ready for review</span><strong>{overview?.counts.draft || 0}</strong><small>Drafts prepared</small></div><div><span>Needs a specialist</span><strong className="orange">{attention}</strong><small>Escalated for human care</small></div><div><span>Sending</span><strong className="control-status">{overview?.kill_switch ? "Paused" : "Enabled"}</strong><small>{overview?.auto_send_enabled ? "Limited automatic mode" : "Operator approval required"}</small></div></section>
  {tab === "Personal setup" && <PersonalSetup onChanged={refresh} openBusiness={() => void switchWorkspace("company")}/>}
  {tab === "Business setup" && <BusinessSetup onChanged={refresh}/> }
  {tab === "Inbox" && <section className="panel"><div className="panel-heading"><div><h2>Conversations <span className="pill">{messages.length}</span></h2><p className="muted">Newest first · Select a conversation to review its evidence.</p></div><label className="search"><span className="sr-only">Search conversations</span><input placeholder="Search conversations…" value={filter} onChange={e => setFilter(e.target.value)}/></label></div><div className="table-wrap"><table><thead><tr><th>Conversation</th><th>Product</th><th>Decision</th><th>Status</th><th>Received</th></tr></thead><tbody>{messages.filter(m => `${m.subject} ${m.sender}`.toLowerCase().includes(filter.toLowerCase())).map(m => <tr key={m.id}><td><button className="subject" onClick={() => action(() => open(m.id), "", false)}><span className="avatar">{m.sender.slice(0, 1).toUpperCase()}</span><span><strong>{m.subject || "(retained ID only)"}</strong><small>{m.sender}</small></span></button></td><td>{m.brand}<small>{m.language.toUpperCase()}</small></td><td><span className={`badge ${m.disposition}`}>{m.disposition}</span></td><td>{m.status.replaceAll("_", " ")}</td><td className="date">{stamp(m.created_at)}</td></tr>)}</tbody></table>{!messages.length && <div className="empty"><h3>Your inbox is clear</h3><p>Seed synthetic demo messages or configure the approved Gmail connector.</p></div>}</div></section>}
  {tab === "Knowledge" && <section className="panel"><div className="panel-heading"><div><h2>Source registry</h2><p className="muted">Only current, approved, customer-safe documents are eligible for retrieval.</p></div>{overview?.mode === "google" && overview.drive_connected && <button disabled={busy} onClick={() => action(() => api("sync/drive", "POST"), "Knowledge sync queued", false)}>Sync Drive</button>}</div><div className="knowledge-grid">{documents.map(d => <article className="document" key={d.id}><span className="document-icon">▧</span><span className={`badge ${d.approved ? "eligible" : "review"}`}>{d.approved ? "Approved" : "Not approved"}</span><h3>{d.title}</h3><p>{d.brand} / {d.model} / {d.language.toUpperCase()}</p><dl><dt>Revision</dt><dd>{d.revision}</dd><dt>Owner</dt><dd>{d.owner}</dd><dt>Visibility</dt><dd>{d.visibility}</dd></dl><a href={safeLink(d.url)} target="_blank" rel="noreferrer">Open original ↗</a>{d.visibility !== "retired" && <button className="text-button" style={{display: "block", marginTop: 16}} disabled={busy} onClick={() => { if (window.confirm("Retire this knowledge source? Existing replies using it will be blocked from sending.")) void action(() => api(`knowledge/${encodeURIComponent(d.id)}/retire`, "POST"), "Knowledge source retired", false); }}>Retire source</button>}</article>)}</div>{!documents.length && <div className="empty">No documents registered. Import approved sources using the API or Drive sync.</div>}</section>}
  {tab === "Activity" && <section className="panel"><div className="panel-heading"><h2>Audit trail</h2><span className="muted">Latest 200 events · Metadata only</span></div><ol className="timeline">{events.map(e => <li key={e.id}><span className="timeline-dot"/><div><strong>{e.event.replaceAll("_", " ")}</strong><p>{e.entity_id} · {e.actor}</p><details><summary>Event details</summary><pre>{JSON.stringify(e.details, null, 2)}</pre></details></div><time>{stamp(e.created_at)}</time></li>)}</ol></section>}
  {tab === "Operations" && <><section className="panel controls"><div><h2>Mailbox kill switch</h2><p>Pause new send reservations for this mailbox. In-flight Gmail requests may still complete.</p></div><button disabled={busy || overview?.draft_only} className={overview?.kill_switch ? "primary" : "danger"} onClick={() => action(() => api("controls", "PUT", { kill_switch: !overview?.kill_switch }), overview?.kill_switch ? "Sending enabled; approval rules still apply" : "Sending paused", false)}>{overview?.kill_switch ? "Enable sending" : "Pause all sending"}</button></section><section className="panel"><div className="panel-heading"><div><h2>Durable jobs</h2><p className="muted">{overview?.pending_jobs} pending / working · {overview?.failed_jobs} failed · Knowledge {overview?.knowledge_sync}</p></div>{overview?.mode === "google" && <button disabled={busy} onClick={() => action(() => api("sync/gmail", "POST"), "Mailbox reconciliation queued", false)}>Reconcile Gmail</button>}</div><div className="table-wrap"><table><thead><tr><th>Job</th><th>Status</th><th>Attempts</th><th>Error type</th></tr></thead><tbody>{jobs.map(j => <tr key={j.id}><td>{j.kind}<small>{j.id}</small></td><td>{j.status}</td><td>{j.attempts}</td><td>{j.error || "—"}</td></tr>)}</tbody></table></div></section></>}
  <footer><span className="dot"/> Draft-first by design<span>SupportFlow AI · Internal pilot v0.1</span></footer></main>
  {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><section role="dialog" aria-modal="true" aria-label="Review conversation" className="drawer" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === "Escape") setSelected(null);
    if (e.key === "Tab") {
      const nodes = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), summary"));
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    } }}><div className="drawer-header"><span className={`badge ${selected.disposition}`}>{selected.disposition}</span><button autoFocus onClick={() => setSelected(null)} aria-label="Close review">✕</button></div><h2>{selected.subject}</h2><p className="muted">{selected.sender} · {selected.brand} {selected.model} · {selected.language.toUpperCase()}</p><div className="mail-body">{selected.body}</div>{selected.risk_tags.length > 0 && <div className="risk"><strong>Human attention required</strong><p>{selected.risk_tags.join(" · ").replaceAll("_", " ")}</p><small>Handle this case through the established support route. Sending here is blocked.{overview?.escalation_email && <> Contact: <a href={`mailto:${overview.escalation_email}`}>{overview.escalation_email}</a>.</>}</small></div>}<div className="ownership"><div><strong>{selected.paused ? "Human owns this thread" : "Agent may prepare drafts"}</strong><small>Gmail human replies also pause automatic sending.</small></div><button disabled={busy} onClick={() => action(() => api(`threads/${encodeURIComponent(selected.thread_id)}/ownership`, "PUT", { paused: !selected.paused, owner: "operator" }), "Thread ownership updated")}>{selected.paused ? "Resume agent" : "Take over"}</button></div><CrmContext key={selected.id} messageId={selected.id} enabled={overview?.mode === "google"}/><h3>Supporting evidence</h3>{selected.citations.map((c, i) => <blockquote key={i}><p>{c.quote}</p><a href={safeLink(c.url)} target="_blank" rel="noreferrer">{c.title} ↗</a><small>Revision {c.revision} · {c.document_id}</small></blockquote>)}{!selected.citations.length && <p className="muted">No verified source. Requires human handling.</p>}<label htmlFor="reply">Response draft</label><textarea id="reply" rows={8} value={response} onChange={e => setResponse(e.target.value)} disabled={busy || selected.status !== "draft"}/><label htmlFor="reason">Review / correction reason</label><input id="reason" value={reason} onChange={e => setReason(e.target.value)} placeholder="Explain your review decision" maxLength={500}/><div className="review-actions"><button disabled={busy || selected.status !== "draft" || selected.risk_tags.length > 0 || reason.trim().length < 3} onClick={() => action(() => api(`messages/${encodeURIComponent(selected.id)}/approve`, "POST", { response, reason }), "Exact response approved and Gmail draft updated")}>Approve response</button><button className="primary" disabled={busy || overview?.draft_only || selected.disposition !== "approved" || selected.response !== response || selected.paused || overview?.kill_switch || selected.status !== "draft"} onClick={() => action(() => api(`messages/${encodeURIComponent(selected.id)}/send`, "POST"), "Reply sent")}>Send approved reply ↗</button></div>{selected.status.includes("uncertain") && <button disabled={busy} onClick={() => action(() => api(`messages/${encodeURIComponent(selected.id)}/reconcile`, "POST"), "Operation reconciled")}>Reconcile with Gmail</button>}<div className="setup-actions">{overview?.mode === "google" && <a className="gmail-link" href={`https://mail.google.com/mail/u/?authuser=${encodeURIComponent(overview.mailbox)}#drafts`} target="_blank" rel="noreferrer">Review drafts in Gmail ↗</a>}</div><p className="muted small">{selected.provider_version} · {selected.status} · {selected.send_state || "No send reserved"}</p></section></div>}
  </div>;
}
