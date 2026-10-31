"use client";
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { workspaceHeaders } from "../../lib/workspace-client";

type Business = { profile: { name: string; industry: string } | null; connectors: Record<string, { configured: boolean; verified: boolean }> };
export default function AssistantOverview({ navigate, active }: { navigate: (tab: string) => void; active: boolean }) {
  const [business, setBusiness] = useState<Business | null>(null), [automatic, setAutomatic] = useState(false);
  const [attention, setAttention] = useState(0), [error, setError] = useState("");
  useEffect(() => {
    async function load() {
      const values = await Promise.all(["business", "automation", "handoffs"].map(async path => {
        const response = await fetch(`/api/backend/${path}`, { headers: workspaceHeaders(), cache: "no-store" });
        const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Unable to load assistant status"); return data;
      }));
      setBusiness(values[0]); setAutomatic(values[1].enabled); setAttention(values[2].filter((h: { active: boolean }) => h.active).length);
    }
    void load().catch(e => setError(e.message));
    const timer = setInterval(() => void load().catch(e => setError(e.message)), 10000); return () => clearInterval(timer);
  }, []);
  const services = [{ key: "google", name: "Gmail & Google Drive", letter: "G", detail: "Customer email and approved knowledge", tone: "blue" }, { key: "gemini", name: "Gemini", letter: "✦", detail: "Answers grounded in your business sources", tone: "purple" }, { key: "salesforce", name: "Salesforce", letter: "S", detail: "Customer activity and support case updates", tone: "blue" }, { key: "netsuite", name: "NetSuite", letter: "N", detail: "Customer activity and case reply logging", tone: "mint" }];
  return <div className="assistant-overview">
    <section className="assistant-hero"><div><span className="hero-label">YOUR TEAM’S AI SUPPORT ASSISTANT</span><h2>Helpful answers.<br/>A human touch when it matters.</h2><p>Teach SupportFlow your business, connect the tools you already use, and automate routine questions. Your team takes over the conversations that need care.</p><div className="setup-actions"><button className="primary" onClick={() => navigate("Business setup")}>{business?.profile ? "Manage assistant" : "Set up your assistant"} <Icon name="handoff"/></button><button onClick={() => navigate("Inbox")}>View conversations</button></div></div><div className="hero-flow" aria-label="Support automation workflow"><div><span className="flow-icon blue"><Icon name="mail"/></span><strong>Customer asks a question</strong><small>Your connected support inbox</small></div><span className="flow-connector" aria-hidden>↓</span><div><span className="flow-icon purple"><Icon name="assistant"/></span><strong>Your knowledge. Your policies.</strong><small>Relevant sources guide every answer</small></div><span className="flow-connector" aria-hidden>↓</span><div><span className="flow-icon mint"><Icon name="check"/></span><strong>Reply, update, or hand over</strong><small>Confirmed sends reach your CRM; people handle exceptions</small></div></div></section>
    {error && <p className="error alert" role="alert">{error}</p>}
    <div className="assistant-summary"><section className="panel"><span className="hero-label">REPLY MODE</span><h3>{automatic && active ? "Automatic replies are active" : automatic ? "Automation is configured" : "Draft review"}</h3><p>{automatic && active ? "Eligible questions are answered within your policy and sender limits." : "Connect your services, approve knowledge and choose when the assistant can send."}</p><button className="text-button" onClick={() => navigate("Business setup")}>Manage reply policy →</button></section><section className="panel"><span className="hero-label">HUMAN HANDOFF</span><h3>{attention ? `${attention} conversation${attention === 1 ? "" : "s"} need your team` : "Your team is in control"}</h3><p>Risky, uncertain and human-requested conversations pause AI replies and notify your configured escalation contact.</p><button className="text-button" onClick={() => navigate("Handoffs")}>Open human handoffs →</button></section></div>
    <section className="panel"><div className="panel-heading"><div><h2>Your connected tools</h2><p className="muted">Use your existing accounts. Choose the services your business needs.</p></div><button onClick={() => navigate("Business setup")}>Manage connections</button></div><div className="service-grid">{services.map(service => {
      const connection = business?.connectors[service.key];
      return <article className="service-card" key={service.key}><span className={`service-mark ${service.tone}`}>{service.letter}</span><h3>{service.name}</h3><p>{service.detail}</p><span className={`badge ${connection?.verified ? "eligible" : "review"}`}>{connection?.verified ? "Verified" : connection?.configured ? "Verify access" : "Not connected"}</span></article>;
    })}</div></section>
    <section className="assistant-principles"><span><Icon name="assistant"/> Business-specific knowledge</span><span><Icon name="check"/> Confirmed CRM updates</span><span><Icon name="handoff"/> Human escalation</span><span><Icon name="shield"/> Separate personal testing</span></section>
  </div>;
}
