"use client";
import DriveKnowledge from "./DriveKnowledge";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Profile = {
  name: string; industry: string; website: string; support_email: string; escalation_email: string;
  languages: string[]; tone: string; escalation_keywords: string[]; acknowledgement: boolean;
};
type Connection = { configured: boolean; fields: Record<string, string>; secret_fields_set: string[]; verified: boolean };
type Setup = { profile: Profile | null; active: boolean; connectors: Record<string, Connection>; checks: Record<string, boolean>; unavailable_integrations: string[] };
const emptyProfile: Profile = { name: "", industry: "General customer support", website: "", support_email: "", escalation_email: "", languages: ["en"], tone: "professional", escalation_keywords: [], acknowledgement: false };
const googleFields = [
  ["mailbox", "Gmail support mailbox", false], ["google_client_id", "Google OAuth client ID", false],
  ["google_client_secret", "Google OAuth client secret", true], ["google_refresh_token", "Google OAuth refresh token", true],
  ["gmail_access_token", "Temporary access token (optional alternative)", true],
  ["drive_folder_id", "Approved Drive folder ID (optional)", false],
  ["gmail_topic", "Pub/Sub topic (optional)", false], ["google_pubsub_audience", "Pub/Sub audience (optional)", false],
  ["google_pubsub_service_account", "Pub/Sub push identity email (optional)", false],
] as const;
const salesforceFields = [["salesforce_client_id", "Salesforce client ID", false], ["salesforce_client_secret", "Salesforce client secret", true], ["salesforce_login_url", "Salesforce login URL (optional; production or sandbox/My Domain)", false]] as const;
const netsuiteFields = [["netsuite_account_id", "NetSuite account ID", false], ["netsuite_client_id", "NetSuite client ID", false], ["netsuite_client_secret", "NetSuite client secret", true]] as const;
const providerFields = { google: googleFields, salesforce: salesforceFields, netsuite: netsuiteFields };
const names: Record<string, string> = { google: "Google Workspace", gemini: "Gemini", salesforce: "Salesforce", netsuite: "NetSuite" };
const geminiFields = [["gemini_api_key", "Gemini API key", true], ["gemini_model", "Approved model ID", false]] as const;

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Operation failed");
  return result;
}
export default function BusinessSetup({ onChanged }: { onChanged: () => Promise<void> }) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [fields, setFields] = useState<Record<string, Record<string, string>>>({ google: {}, gemini: {} });
  const [oauth, setOauth] = useState<{ available: boolean; redirect_uris: Record<string, string> }>({ available: false, redirect_uris: {} });
  const [keywords, setKeywords] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [knowledge, setKnowledge] = useState({ title: "", brand: "", model: "general", language: "en", owner: "", url: "", customer_url: "", content: "", approved: false });
  const load = useCallback(async () => {
    const [result, oauthSettings] = await Promise.all([api<Setup>("business"), api<{ available: boolean; redirect_uris: Record<string, string> }>("business/oauth")]);
    setOauth(oauthSettings);
    setSetup(result);
    if (result.profile) { setProfile(result.profile); setKeywords(result.profile.escalation_keywords.join(", ")); }
    setFields(Object.fromEntries(Object.entries(result.connectors).map(([key, connection]) => [key, connection.fields])));
  }, []);
  useEffect(() => {
    load().catch(e => setError(e.message));
    const query = new URLSearchParams(window.location.search);
    if (query.has("connection")) {
      setNotice(query.get("result") === "connected" ? "Account connected securely. Verify access, select approved knowledge, then activate draft-only processing." : "Account authorization was not completed. Check app/client configuration, exact callback URL, permissions and selected account, then reconnect.");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [load]);
  const connect = async (provider: string) => {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/oauth/start/${provider}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Cannot start sign-in");
      window.location.assign(data.authorization_url);
    } catch (e) { setError(e instanceof Error ? e.message : "Connection failed"); setBusy(false); }
  };
  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); await load(); await onChanged(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "Operation failed"); }
    finally { setBusy(false); }
  };
  const saveProfile = (event: FormEvent) => {
    event.preventDefault();
    void run(() => api("business/profile", "PUT", { ...profile, escalation_keywords: keywords.split(",").map(v => v.trim()).filter(Boolean) }), "Company profile saved. Processing is paused until you activate draft-only mode.");
  };
  const addKnowledge = (event: FormEvent) => {
    event.preventDefault();
    const body = { ...knowledge, id: "manual-" + crypto.randomUUID(), revision: new Date().toISOString(), effective_at: new Date().toISOString(), visibility: "customer_safe", expires_at: null };
    void run(async () => { await api("knowledge", "PUT", body); setKnowledge({ ...knowledge, title: "", content: "", approved: false }); }, "Knowledge source saved. Only approved, current sources are retrieved.");
  };
  const checklist: Record<string, string> = { company_profile: "Company profile saved", google_verified: "Google mailbox / optional Drive verified", gemini_verified: "Gemini access verified", approved_knowledge: "Approved business knowledge added", policy_acknowledged: "Review and data-processing policy acknowledged" };
  return <div className="setup-workspace">
    <section className="panel setup-intro"><span className="tag">BUSINESS ONBOARDING</span><h2>Make this workspace yours</h2><p>Configure one company per isolated deployment and database. Connect supported services when you are ready. Unconfigured integrations stay inactive.</p><div className="workflow-strip"><span>Customer email</span><b>→</b><span>Approved Drive knowledge</span><b>→</b><span>Gemini draft</span><b>→</b><span>Human review + optional CRM</span><b>→</b><span>Reply in Gmail</span></div><p className="muted">Live activation is draft-only. A person sends approved replies through your existing support process. Free hosting may sleep; use always-on hosting before connecting customer mailboxes.</p></section>
    {error && <div className="error alert" role="alert">{error}</div>}{notice && <div className="notice alert" role="status">{notice}</div>}
    <section className="panel setup-section"><h2>1. Company and policies</h2><form onSubmit={saveProfile}>
      <div className="setup-grid">{([ ["name", "Company name", "text"], ["industry", "Industry / business type", "text"], ["website", "Company website (optional HTTPS URL)", "url"], ["support_email", "Support mailbox", "email"], ["escalation_email", "Human escalation contact", "email"] ] as const).map(([key, label, type]) => <label key={key}>{label}<input type={type} required={key !== "website"} maxLength={key === "name" || key === "industry" ? 120 : key === "website" ? 500 : 320} value={profile[key]} onChange={e => setProfile({ ...profile, [key]: e.target.value })}/></label>)}
      <label>Response tone<select value={profile.tone} onChange={e => setProfile({ ...profile, tone: e.target.value })}><option value="professional">Professional</option><option value="friendly">Friendly</option><option value="concise">Concise</option></select></label></div>
      <fieldset><legend>Supported languages</legend>{[["en", "English"], ["de", "German"]].map(([code, label]) => <label className="check-label" key={code}><input type="checkbox" checked={profile.languages.includes(code)} onChange={e => setProfile({ ...profile, languages: e.target.checked ? [...profile.languages, code] : profile.languages.filter(v => v !== code) })}/>{label}</label>)}</fieldset>
      <label>Additional human-review keywords (comma separated)<input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="Your business-specific escalation topics"/></label>
      <label className="check-label policy-ack"><input type="checkbox" checked={profile.acknowledgement} onChange={e => setProfile({ ...profile, acknowledgement: e.target.checked })}/>I am authorized to connect this company’s data, have reviewed provider/privacy terms, and will keep replies under human review. Regulated or high-risk cases require specialist policies.</label>
      <button className="primary" disabled={busy || !profile.languages.length}>Save company profile</button>
    </form></section>
    <section className="panel setup-section"><h2>2. Connect your services</h2><p className="muted">Connect Gmail and Drive for email and knowledge. Add Salesforce and NetSuite optionally for read-only reviewer context. An administrator registers each OAuth app/client once; then use Connect to sign in directly with the provider. Verification sends no customer email.</p>
      <div className="connector-grid">{["google", "gemini", "salesforce", "netsuite"].map(key => {
        const inputs = key === "gemini" ? geminiFields : providerFields[key as keyof typeof providerFields];
        const field = ([name, label, secret]: readonly [string, string, boolean]) => <label key={name}>{label}<input type={secret ? "password" : "text"} autoComplete="off" value={fields[key]?.[name] || ""} placeholder={secret && setup?.connectors[key]?.secret_fields_set.includes(name) ? "Saved securely — leave blank to keep" : ""} onChange={e => setFields({ ...fields, [key]: { ...fields[key], [name]: e.target.value } })}/></label>;
        return <article className="connector-card" key={key}>
        <div className="connector-heading"><h3>{names[key]}</h3><span className={`badge ${setup?.connectors[key]?.verified ? "eligible" : "review"}`}>{setup?.connectors[key]?.verified ? "Verified" : setup?.connectors[key]?.configured ? "Needs verification" : "Not connected"}</span></div>
        {key === "salesforce" && fields[key]?.salesforce_instance_url && <small>Connected organization: {fields[key].salesforce_instance_url}</small>}<p className="muted small">{key === "google" ? "Read Gmail, prepare threaded drafts, and browse approved Drive sources." : key === "gemini" ? "Generate answers from approved evidence. Subject to your model/privacy approval." : "Optional. Read-only customer lookup in the review screen; no record changes or automatic customer disclosures."}</p>
        <form onSubmit={event => { event.preventDefault(); void run(() => api(`business/connectors/${key}`, "PUT", { fields: fields[key] || {} }), "Connection saved encrypted. Verify access before activation."); }}>
          {key === "gemini" ? inputs.map(field) : <>
            {key === "google" && inputs.filter(([name]) => ["mailbox", "drive_folder_id"].includes(name)).map(field)}
            {key === "netsuite" && inputs.filter(([name]) => name === "netsuite_account_id").map(field)}
            <details className="admin-setup"><summary>Administrator setup — one time</summary><p className="muted small">Register a provider OAuth client with this exact callback URL. Never enter your account password here.</p>{oauth.redirect_uris[key] && <label>OAuth callback URL<input readOnly value={oauth.redirect_uris[key]}/></label>}
              {inputs.filter(([name]) => !(key === "google" && ["mailbox", "drive_folder_id"].includes(name)) && !(key === "netsuite" && name === "netsuite_account_id")).map(field)}
            </details>
          </>}
          <div className="setup-actions"><button disabled={busy}>Save connection</button>{key !== "gemini" && <button className="primary" type="button" disabled={busy || !oauth.available || !setup?.connectors[key]?.configured} onClick={() => void connect(key)}>Connect {key === "google" ? "Google account" : names[key]}</button>}<button type="button" disabled={busy || !setup?.connectors[key]?.configured} onClick={() => void run(() => api(`business/connectors/${key}/verify`, "POST"), "Access verified. Verification is valid for 24 hours for activation.")}>Verify access</button><button type="button" className="danger" disabled={busy || !setup?.connectors[key]?.configured} onClick={() => { if (window.confirm("Disconnect this provider and pause processing? Stored credentials will be removed.")) void run(() => api(`business/connectors/${key}`, "DELETE"), "Disconnected. Credentials removed and processing paused."); }}>Disconnect</button></div>
          {!oauth.available && key !== "gemini" && <small>Set PUBLIC_APP_URL to enable account sign-in. Render configures the callback origin automatically.</small>}
        </form>
      </article>; })}</div>
      <p className="muted">Not available in this release: {setup?.unavailable_integrations.join(", ") || "Microsoft 365, Shopify, WhatsApp"}. These services cannot be connected with this version.</p>
    </section>
    <section className="panel setup-section"><h2>3. Add approved business knowledge</h2><div className="notebook-note"><strong>Using NotebookLM?</strong><p>Connect the original Google Drive documents used as notebook sources. NotebookLM conversations and generated answers are not imported as authoritative knowledge. For local notebook files, upload the original PDF/Docs/Markdown to your approved Drive folder, or paste reviewed text below.</p></div><DriveKnowledge company={profile.name} onChanged={async () => { await load(); await onChanged(); }}/><details className="manual-knowledge"><summary>Or paste an approved source manually</summary><p className="muted">Paste an approved policy, FAQ, or product reference. Use your company name as the business family and “general” for company-wide policies. Product-specific sources should use the exact product name/model. Drive folder sources can also sync after activation.</p><form onSubmit={addKnowledge}>
      <div className="setup-grid">{([ ["title", "Source title"], ["brand", "Business / product family"], ["model", "Product model or general"], ["owner", "Knowledge owner"], ["url", "Internal source URL (HTTPS)"], ["customer_url", "Customer-facing URL (optional HTTPS)"] ] as const).map(([key, label]) => <label key={key}>{label}<input required={key !== "customer_url"} type={key.endsWith("url") ? "url" : "text"} maxLength={key === "brand" ? 40 : key === "model" ? 100 : key === "title" ? 500 : key === "owner" ? 200 : 1000} value={knowledge[key]} onChange={e => setKnowledge({ ...knowledge, [key]: e.target.value })}/></label>)}
      <label>Source language<select value={knowledge.language} onChange={e => setKnowledge({ ...knowledge, language: e.target.value })}><option value="en">English</option><option value="de">German</option></select></label></div>
      <label>Approved source text<textarea required minLength={15} maxLength={200000} rows={7} value={knowledge.content} onChange={e => setKnowledge({ ...knowledge, content: e.target.value })}/></label>
      <label className="check-label"><input type="checkbox" checked={knowledge.approved} onChange={e => setKnowledge({ ...knowledge, approved: e.target.checked })}/>This source is current, reviewed, and safe for customers.</label><button disabled={busy}>Save knowledge source</button>
    </form></details></section>
    <section className="panel setup-section"><h2>4. Readiness and activation</h2><ul className="readiness-list">{Object.entries(checklist).map(([key, label]) => <li key={key}><span className={`badge ${setup?.checks[key] ? "eligible" : "review"}`}>{setup?.checks[key] ? "Complete" : "Required"}</span>{label}</li>)}</ul><p>{setup?.active ? "Draft processing is active. Sending remains disabled in this setup." : "Processing is paused. Saving changes pauses processing and resets affected connection verification."}</p><div className="setup-actions"><button className="primary" disabled={busy || !setup || !Object.values(setup.checks).every(Boolean) || setup.active} onClick={() => { if (window.confirm("Activate draft-only processing? This reads the configured Gmail mailbox and sends bounded email content to your configured Gemini provider. No email will be sent.")) void run(() => api("business/activate", "POST"), "Draft-only processing activated. The worker will pick up the settings automatically."); }}>Activate draft-only processing</button><button disabled={busy || !setup?.active} onClick={() => void run(() => api("business/pause", "POST"), "Processing paused; new worker jobs wait until activation.")}>Pause processing</button></div></section>
  </div>;
}
