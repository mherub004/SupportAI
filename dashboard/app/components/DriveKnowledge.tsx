"use client";
import { FormEvent, useState } from "react";

type FileRow = { id: string; title: string; mime_type: string; revision: string; modified_time: string; approved: boolean };
type Preview = FileRow & { content: string };
async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Drive request failed");
  return result;
}
export default function DriveKnowledge({ company, onChanged, personalOwner }: { company: string; onChanged: () => Promise<void>; personalOwner?: string }) {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [metadata, setMetadata] = useState({ brand: company.slice(0, 40), model: "general", language: "en", owner: personalOwner || "", customer_url: "", approved: false });
  async function browse() {
    setBusy(true); setError(""); setNotice("");
    try { setFiles(await api<FileRow[]>("business/drive/files")); setNotice("Folder loaded. Preview and approve each exact document version before it can ground replies."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load folder"); }
    finally { setBusy(false); }
  }
  async function open(file: FileRow) {
    setBusy(true); setError(""); setNotice(""); setPreview(null);
    try { setPreview(await api<Preview>(`business/drive/files/${encodeURIComponent(file.id)}`)); setMetadata({ ...metadata, approved: false }); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to preview source"); }
    finally { setBusy(false); }
  }
  async function approve(event: FormEvent) {
    event.preventDefault(); if (!preview) return;
    setBusy(true); setError("");
    try {
      await api(`business/drive/files/${encodeURIComponent(preview.id)}/approve`, "POST", { ...metadata, revision: preview.revision, modified_time: preview.modified_time });
      setPreview(null); setFiles(files.map(file => file.id === preview.id ? { ...file, approved: true } : file));
      await onChanged(); setNotice("Source imported. If the Drive file changes, it must be reviewed and approved again.");
    } catch (e) { setError(e instanceof Error ? e.message : "Import failed"); }
    finally { setBusy(false); }
  }
  return <div className="drive-browser"><h3>Import from your approved Drive folder</h3><p className="muted">Save a folder ID or folder link in Google Workspace above, verify access, then browse its Docs, PDFs, Markdown and text files. Imports can be approved before activating Gmail processing.</p><button type="button" disabled={busy} onClick={() => void browse()}>Browse Google Drive folder</button>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice alert" role="status">{notice}</p>}
    {files.length > 0 && <ul className="drive-file-list">{files.map(file => <li key={file.id}><div><strong>{file.title}</strong><small>Revision {file.revision} · {file.approved ? "Approved" : "Needs review"}</small></div><button disabled={busy || !["application/vnd.google-apps.document", "text/plain", "text/markdown", "application/pdf"].includes(file.mime_type)} type="button" onClick={() => void open(file)}>Preview</button></li>)}</ul>}
    {preview && <form className="source-preview" onSubmit={approve}><h3>{preview.title}</h3><small>Revision {preview.revision} · Internal preview, not sent to Gemini during import</small><label>Extracted source preview<textarea readOnly rows={8} value={preview.content}/></label><div className="setup-grid">
      {!personalOwner && <><label>Drive source business / product family<input required maxLength={40} value={metadata.brand} onChange={e => setMetadata({ ...metadata, brand: e.target.value })}/></label>
      <label>Drive source model or general<input required maxLength={100} value={metadata.model} onChange={e => setMetadata({ ...metadata, model: e.target.value })}/></label>
      <label>Drive source knowledge owner<input required maxLength={200} value={metadata.owner} onChange={e => setMetadata({ ...metadata, owner: e.target.value })}/></label></>}
      <label>Drive source language<select value={metadata.language} onChange={e => setMetadata({ ...metadata, language: e.target.value })}><option value="en">English</option><option value="de">German</option></select></label>
      {!personalOwner && <label>Drive source customer-facing URL (optional)<input type="url" value={metadata.customer_url} onChange={e => setMetadata({ ...metadata, customer_url: e.target.value })}/></label>}
    </div><label className="check-label"><input type="checkbox" checked={metadata.approved} onChange={e => setMetadata({ ...metadata, approved: e.target.checked })}/>I reviewed this exact version and approve it for customer-safe answers.</label><div className="setup-actions"><button className="primary" disabled={busy || !metadata.approved}>Approve and import source</button><button type="button" disabled={busy} onClick={() => setPreview(null)}>Cancel preview</button></div></form>}
  </div>;
}
