"use client";
import AutomationControls from "./AutomationControls";
import { workspaceHeaders } from "../../lib/workspace-client";
import { useCallback, useEffect, useState } from "react";
import DriveKnowledge from "./DriveKnowledge";

type Connection = { configured: boolean; verified: boolean; fields: Record<string, string>; secret_fields_set: string[] };
type Setup = { sending_mode?: string; personal: boolean; personal_available: boolean; active: boolean; profile: (Record<string, unknown> & { name: string }) | null; checks: Record<string, boolean>; connectors: Record<string, Connection> };
async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { method, cache: "no-store", headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Request failed"); return data;
}
export default function PersonalSetup({ onChanged, openBusiness }: { onChanged: () => Promise<void>; openBusiness: () => void }) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [oauth, setOauth] = useState<{ available: boolean; google_ready: boolean; provider_ready?: Record<string, boolean>; redirect_uris?: Record<string, string> }>({ available: false, google_ready: false });
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [folder, setFolder] = useState(""), [folders, setFolders] = useState<{ id: string; name: string }[]>([]);
  const [key, setKey] = useState(""), [model, setModel] = useState("gemini-2.5-flash"), [consent, setConsent] = useState(false);
  const load = useCallback(async () => {
    const [s, o] = await Promise.all([api<Setup>("business"), api<typeof oauth>("business/oauth")]);
    setSetup(s); setOauth(o); setFolder(s.connectors.google.fields.drive_folder_id || "");
    setModel(s.connectors.gemini.fields.gemini_model || "gemini-2.5-flash");
  }, []);
  useEffect(() => {
    void load().catch(e => setError(e.message));
  }, [load]);
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await load(); await onChanged(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "Operation failed"); }
    finally { setBusy(false); }
  }
  async function connect(provider = "google") {
    if (provider === "google" && setup?.profile && !setup.personal && !window.confirm("Start personal testing in this workspace? This replaces the saved company profile with your selected Google account. Existing knowledge is kept. No live company mail has been imported.")) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/oauth/start/${provider}`, { method: "POST", headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ personal: provider === "google" }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Cannot connect Google"); window.location.assign(data.authorization_url);
    } catch (e) { setError(e instanceof Error ? e.message : "Sign-in failed"); setBusy(false); }
  }
  if (setup && !setup.personal_available) return <section className="panel setup-section"><h2>This installation has live business mail</h2><p>Use its existing business setup. Personal testing needs its own installation so mailbox data stays separate.</p><button onClick={openBusiness}>Open business setup</button></section>;
  const google = setup?.connectors.google, gemini = setup?.connectors.gemini;
  const ready = setup?.personal && ["company_profile", "approved_knowledge", "google_verified", "gemini_verified"].every(k => setup.checks[k]);
  return <div className="setup-workspace personal-setup">
    <section className="panel setup-intro"><span className="tag">PERSONAL TEST</span><h2>Connect your inbox. Choose your knowledge. Try a reply.</h2><p>One Google account, your selected knowledge and your Gemini API key. No company form or CRM required.</p><div className="workflow-strip"><span>Connect Google</span><b>→</b><span>Choose knowledge</span><b>→</b><span>Add Gemini key</span><b>→</b><span>Test automatic replies</span></div><p className="muted">Use a test Gmail: initial sync reads the last seven days of inbox mail. This installation stays tied to that mailbox. Choose draft review or automatic replies to your allowed test senders below.</p><button className="text-button" onClick={openBusiness}>Need company policies or CRM? Open business setup</button></section>
    {error && <p className="error alert" role="alert">{error}</p>}{notice && <p className="notice alert" role="status">{notice}</p>}
    <section className="panel setup-section"><h2>1. Connect Google</h2><p>{google?.fields.mailbox ? `Selected account: ${google.fields.mailbox}` : "Choose the Gmail account you want to test on Google’s sign-in screen."}</p>
      {!oauth.google_ready && <div className="notice alert"><strong>Google sign-in needs hosting setup</strong><p>The deployment owner registers a Google OAuth Web client once and sets GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the backend host. Register the test callback below. Company credentials and mailbox tokens are not copied into this environment.</p>{oauth.redirect_uris?.google && <label>Personal test Google callback<input readOnly value={oauth.redirect_uris.google}/></label>}<a href="https://github.com/mherub004/SupportAI/blob/main/docs/PERSONAL_QUICKSTART.md" target="_blank" rel="noreferrer">Host setup instructions</a></div>}
      <div className="setup-actions"><button className="primary" disabled={busy || !oauth.available || !oauth.google_ready} onClick={() => void connect()}>{google?.fields.mailbox ? "Reconnect Google" : "Connect Google"}</button>{google?.configured && <><button disabled={busy} onClick={() => void run(() => api("business/connectors/google/verify", "POST"), "Google access verified.")}>Verify Google access</button><button className="danger" disabled={busy} onClick={() => { if (window.confirm("Disconnect Google and pause processing? Existing Gmail drafts remain.")) void run(() => api("business/connectors/google", "DELETE"), "Google disconnected. Processing paused."); }}>Disconnect Google</button></>}</div>
    </section>
    <section className="panel setup-section"><h2>2. Choose your knowledge</h2><p>Select a Drive folder, then preview and approve the files you want used for answers. Only supported direct-child files are imported; NotebookLM users should choose their original source documents.</p>
      <button disabled={busy || !google?.verified} onClick={() => void run(async () => { const result = await api<{ folders: { id: string; name: string }[]; has_more: boolean }>("personal/drive-folders"); setFolders(result.folders); if (result.has_more) setNotice("Showing the first 100 folders. Paste a link for another folder."); }, "Folders loaded (up to 100). You can also paste a folder link.")}>Choose from my Drive folders</button>
      {folders.length > 0 && <label>Available Drive folders<select value={folder} onChange={e => setFolder(e.target.value)}><option value="">Choose a folder</option>{folders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>}
      <form onSubmit={e => { e.preventDefault(); void run(async () => { await api("business/connectors/google", "PUT", { fields: { drive_folder_id: folder } }); await api("business/connectors/google/verify", "POST"); }, "Knowledge folder saved and access verified. Preview and approve your files below."); }}><label>Drive folder link or ID<input required value={folder} onChange={e => setFolder(e.target.value)} placeholder="Paste a folder link or choose above"/></label><button disabled={busy || !google?.fields.mailbox}>Use this knowledge folder</button></form>
      {setup?.personal && google?.fields.drive_folder_id && <DriveKnowledge key={google.fields.drive_folder_id} company={setup.profile?.name || "Personal inbox"} personalOwner={google.fields.mailbox} onChanged={async () => { await load(); await onChanged(); }}/>}<p className="muted">You can also use approved knowledge already imported through the authenticated API. Never put API credentials into a knowledge document.</p>
    </section>
    <section className="panel setup-section"><h2>3. Add your Gemini API key</h2><form onSubmit={e => { e.preventDefault(); void run(async () => { await api("business/connectors/gemini", "PUT", { fields: { gemini_api_key: key, gemini_model: model } }); setKey(""); await api("business/connectors/gemini/verify", "POST"); }, "Gemini key saved securely and verified."); }}><label>Personal Gemini API key<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder={gemini?.secret_fields_set.includes("gemini_api_key") ? "Saved securely — leave blank to keep" : "Enter your Gemini API key"}/></label><label>Gemini model<input required value={model} onChange={e => setModel(e.target.value)}/></label><button disabled={busy}>Save and verify Gemini</button></form></section>
    <details className="panel setup-section"><summary>Optional: connect Salesforce or NetSuite</summary><p>Sign in for customer context. Select a provider in reply automation to log confirmed sends against its customer and case. These connections are optional for a Gmail-only test.</p><div className="connector-grid">{["salesforce", "netsuite"].map(provider => {
      const connection = setup?.connectors[provider];
      const name = provider === "salesforce" ? "Salesforce" : "NetSuite";
      return <article className="connector-card" key={provider}><h3>{name}</h3><p>{connection?.verified ? "Access verified" : "Connect your account, then verify access."}</p>
        {!oauth.provider_ready?.[provider] && <p className="muted">The host must configure this provider’s OAuth integration first{provider === "netsuite" ? ", including your NetSuite account ID" : ""}. <a href="https://github.com/mherub004/SupportAI/blob/main/docs/PERSONAL_QUICKSTART.md" target="_blank" rel="noreferrer">Host setup instructions</a></p>}
        <div className="setup-actions"><button className="primary" disabled={busy || !oauth.available || !oauth.provider_ready?.[provider]} onClick={() => void connect(provider)}>Connect {name}</button><button disabled={busy || !connection?.configured} onClick={() => void run(() => api(`business/connectors/${provider}/verify`, "POST"), `${name} access verified.`)}>Verify {name} access</button><button className="danger" disabled={busy || !connection?.configured} onClick={() => { if (window.confirm(`Disconnect ${name}? Gmail processing stays available.`)) void run(() => api(`business/connectors/${provider}`, "DELETE"), `${name} disconnected.`); }}>Disconnect {name}</button></div></article>;
    })}</div></details>
    <AutomationControls personal onChanged={async () => { await load(); await onChanged(); }}/>
    <section className="panel setup-section"><h2>4. Start your email test</h2><p>Google: {google?.verified ? "verified" : "required"} · Knowledge: {setup?.checks.approved_knowledge ? "approved" : "required"} · Gemini: {gemini?.verified ? "verified" : "required"}</p><label className="check-label"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>I authorize processing this mailbox and sending email text and approved knowledge excerpts to my Gemini provider. My saved automation policy controls whether replies remain drafts or are sent to allowed test accounts.</label><div className="setup-actions"><button className="primary" disabled={busy || !ready || !consent || setup?.active} onClick={() => void run(async () => { await api("business/profile", "PUT", { ...setup?.profile, acknowledgement: true }); await api("business/activate", "POST"); }, "Personal testing active under your saved reply policy. Send a question from your allowed second account, then check delivery in both inboxes.")}>{setup?.sending_mode === "automatic" ? "Start automatic email test" : "Start personal test"}</button><button disabled={busy || !setup?.active} onClick={() => void run(() => api("business/pause", "POST"), "Processing paused.")}>Pause test</button></div><p>{setup?.active ? "Email processing is active under your saved policy. Send a fresh email from your allowed second account after activation; keep the service awake during testing." : "Processing is paused until you complete the steps above."}</p></section>
  </div>;
}
