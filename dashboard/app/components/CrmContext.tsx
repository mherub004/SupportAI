"use client";
import { workspaceHeaders } from "../../lib/workspace-client";
import { useState } from "react";
type Result = { providers: Record<string, { status: string; records: { record_id: string; display_name: string; organization: string }[] }>; warning: string };
export default function CrmContext({ messageId, enabled }: { messageId: string; enabled: boolean }) {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setError(""); setResult(null);
    try {
      const response = await fetch(`/api/backend/messages/${encodeURIComponent(messageId)}/crm-context`, { method: "POST", headers: { ...workspaceHeaders(), "Content-Type": "application/json" }, body: "{}" });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "CRM lookup failed"); setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load context"); }
    finally { setBusy(false); }
  }
  return <section className="crm-review"><h3>CRM context for internal review</h3><p className="muted">Look up the incoming sender in verified Salesforce/NetSuite connections. An email match does not prove identity. These facts are never inserted into AI replies automatically.</p><button type="button" disabled={busy || !enabled} onClick={() => void load()}>{busy ? "Looking up…" : "Load read-only CRM context"}</button>{!enabled && <small>Available for your business’s real Gmail messages after activation.</small>}{error && <p role="alert" className="error">{error}</p>}{result && <><p className="risk small">{result.warning}</p>{Object.entries(result.providers).map(([provider, value]) => <article className="crm-record" key={provider}><strong>{provider === "salesforce" ? "Salesforce" : "NetSuite"}</strong><span className="badge">{value.status.replaceAll("_", " ")}</span>{value.records.map(record => <dl key={record.record_id}><dt>Record</dt><dd>{record.record_id}</dd><dt>Name</dt><dd>{record.display_name}</dd><dt>Company</dt><dd>{record.organization}</dd></dl>)}</article>)}</>}</section>;
}
