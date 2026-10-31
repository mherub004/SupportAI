"use client";
import { useEffect, useState } from "react";
import { workspaceHeaders } from "../../lib/workspace-client";

type Policy = { enabled: boolean; acknowledgement: boolean; allowed_senders: string[]; hourly_limit: number; crm_providers: string[] };
type Delivery = { message_id: string; provider: string; status: string; activity_state: string; case_state: string; error: string; case_id: string };
async function api<T>(path: string, method = "GET", data?: unknown): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { method, headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, cache: "no-store", body: data === undefined ? undefined : JSON.stringify(data) });
  const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Automation request failed"); return result;
}
export default function AutomationControls({ personal = false, onChanged }: { personal?: boolean; onChanged: () => Promise<void> }) {
  const [policy, setPolicy] = useState<Policy>({ enabled: false, acknowledgement: false, allowed_senders: [], hourly_limit: 10, crm_providers: [] });
  const [senders, setSenders] = useState(""), [deliveries, setDeliveries] = useState<Delivery[]>([]), [cases, setCases] = useState<Record<string, string>>({});
  const [netSuiteField, setNetSuiteField] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  useEffect(() => {
    api<Policy>("automation").then(p => { setPolicy(p); setSenders(p.allowed_senders.join(", ")); }).catch(e => setError(e.message));
    api<{ connectors: Record<string, { fields: Record<string, string> }> }>("business").then(result => setNetSuiteField(result.connectors?.netsuite?.fields?.netsuite_case_reply_field || "")).catch(e => setError(e.message));
    const refresh = () => api<Delivery[]>("automation/deliveries").then(setDeliveries).catch(e => setError(e.message));
    void refresh(); const timer = setInterval(refresh, 10000); return () => clearInterval(timer);
  }, []);
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setDeliveries(await api<Delivery[]>("automation/deliveries")); await onChanged(); setNotice(message); }
    catch (e) { setError(e instanceof Error ? e.message : "Automation failed"); }
    finally { setBusy(false); }
  }
  return <section className="panel setup-section"><h2>Automatic replies and CRM updates</h2><p>Answer eligible support questions using approved knowledge. Safety, refund, identity-sensitive, uncertain and ungrounded cases remain for human handling. After Gmail confirms sending, a separate job logs the customer activity and updates its case. CRM retries never resend email.</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="notice alert">{notice}</p>}
    <form onSubmit={e => { e.preventDefault(); void run(async () => {
      if (policy.crm_providers.includes("netsuite") && netSuiteField) {
        await api("business/connectors/netsuite", "PUT", { fields: { netsuite_case_reply_field: netSuiteField } });
        await api("business/connectors/netsuite/verify", "POST");
      }
      await api("automation", "PUT", { ...policy, allowed_senders: senders.split(",").map(s => s.trim()).filter(Boolean) });
    }, "Policy saved. Processing is paused: use the activation button below to apply it."); }}>
      <label className="check-label"><input type="checkbox" checked={policy.enabled} onChange={e => setPolicy({ ...policy, enabled: e.target.checked })}/>Automatically send eligible support replies</label>
      <div className="setup-grid"><label>{personal ? "Allowed test sender emails (required for automatic testing)" : "Allowed sender emails (optional restriction)"}<input value={senders} onChange={e => setSenders(e.target.value)} placeholder="second-account@example.com" required={personal && policy.enabled}/></label><label>Maximum replies per hour<input type="number" min={1} max={100} required value={policy.hourly_limit} onChange={e => setPolicy({ ...policy, hourly_limit: Number(e.target.value) })}/></label></div>
      <fieldset><legend>After sending, update customer activity and case</legend>{["salesforce", "netsuite"].map(provider => <label className="check-label" key={provider}><input type="checkbox" checked={policy.crm_providers.includes(provider)} onChange={e => setPolicy({ ...policy, crm_providers: e.target.checked ? [...policy.crm_providers, provider] : policy.crm_providers.filter(p => p !== provider) })}/>{provider === "salesforce" ? "Salesforce" : "NetSuite"}</label>)}</fieldset>
      {policy.crm_providers.includes("netsuite") && <label>NetSuite dedicated case reply field<input value={netSuiteField} maxLength={100} onChange={e => setNetSuiteField(e.target.value)} placeholder="custevent_supportflow_last_reply"/><small>Use an existing writable custom text field on support cases. Its schema and permissions are verified before enabling writes.</small></label>}
      <p className="muted">Selected CRMs must be connected and verified with write permissions. Salesforce creates a completed Task and private CaseComment. NetSuite creates a customer Task and updates the dedicated case reply field configured in its connector. Cases are not automatically closed.</p>
      <label className="check-label"><input type="checkbox" checked={policy.acknowledgement} onChange={e => setPolicy({ ...policy, acknowledgement: e.target.checked })}/>I authorize automatic email sending under this policy and the selected CRM writes.</label><button disabled={busy || (policy.enabled && !policy.acknowledgement)}>Save reply automation</button>
    </form>
    {deliveries.length > 0 && <><h3>CRM delivery status</h3><p>Missing or ambiguous matches need a verified case selection. An uncertain external write needs inspection in the CRM; it cannot be blindly retried.</p><div className="table-wrap"><table><thead><tr><th>Email / CRM</th><th>Customer activity</th><th>Support case</th><th>Result</th><th>Action</th></tr></thead><tbody>{deliveries.map(d => {
      const key = `${d.provider}:${d.message_id}`, uncertain = d.activity_state === "reserved" || d.case_state === "reserved";
      const path = `automation/deliveries/${encodeURIComponent(d.message_id)}/${d.provider}`;
      return <tr key={key}><td>{d.message_id}<small>{d.provider}</small></td><td>{d.activity_state}</td><td>{d.case_state}</td><td>{d.status}<small>{d.error}</small></td><td>{d.status !== "done" && !uncertain && <><button disabled={busy || d.status === "working"} onClick={() => void run(() => api(`${path}/retry`, "POST"), "CRM retry queued. Email will not be resent.")}>Retry CRM update</button>{d.activity_state !== "done" && <><input aria-label={`Case ID for ${key}`} value={cases[key] || ""} onChange={e => setCases({ ...cases, [key]: e.target.value })} placeholder="Existing CRM case ID"/><button disabled={busy || !cases[key]} onClick={() => void run(() => api(`${path}/case`, "PUT", { case_id: cases[key] }), "Case ownership verified and CRM update queued.")}>Verify and use case</button></>}</>}{uncertain && <><p>Inspect external write before continuing</p><input aria-label={`External CRM record ID for ${key}`} value={cases[key] || ""} onChange={e => setCases({ ...cases, [key]: e.target.value })} placeholder="Confirmed CRM activity/comment ID"/><button disabled={busy || d.status === "working"} onClick={() => void run(() => api(`${path}/reconcile`, "POST", { external_id: cases[key] || "" }), "External write verified against its delivery marker. No email was resent.")}>Verify existing external write</button></>}</td></tr>;
    })}</tbody></table></div></>}
  </section>;
}
