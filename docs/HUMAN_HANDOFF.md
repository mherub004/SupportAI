# Human handoff alongside your existing support tools

SupportFlow handles routine questions using approved business knowledge. It works beside your existing helpdesk: Gmail delivers replies, Salesforce/NetSuite retain customer and case logs, and your team handles exceptions. The lighter **Assistant** home shows reply mode, handoffs and actual connection status. The company and personal test areas remain separate.

## Set up and test

1. In **Business setup**, save your business name, support mailbox, escalation email, language, tone and escalation keywords. Use an escalation address that your team controls. For a personal test, this can be your own address.
2. Connect Google, select and approve your knowledge, then save and verify Gemini. Connect Salesforce/NetSuite only if you need CRM logging. The host's one-time OAuth application registration enables the Google, Salesforce and NetSuite consent buttons; ChatGPT's connected accounts cannot authorize SupportFlow. See [personal quickstart](PERSONAL_QUICKSTART.md) and [automation setup](AUTOMATION.md).
3. Choose draft review or explicitly enable automatic replies. For a personal automatic test, allow only your second sender account. Activate processing and send a fresh question from that account.
4. Ask to speak to a human, or ask something outside the approved knowledge. The conversation pauses for human ownership and appears under **Handoffs**. It cannot receive an automatic customer reply while paused.
5. The configured escalation contact receives an internal Gmail notification with the original sender, subject, reasons and a link to the Gmail conversation. The full customer body is omitted. The alert is a separate email with automation headers, so it does not become a reply to the customer or trigger an email loop.
6. Choose **Review conversation** to inspect the original message and evidence. Your agent responds through your existing Gmail/helpdesk workflow. Choose **Resume assistant** when human handling is complete. This resolves the active handoff and permits new incoming messages under the current reply policy; it does not replay the held customer message.

Configured business escalation rules, human requests, detected risk, uncertain answers and unavailable grounding trigger handoff. CRM customer/case ambiguity, uncertain writes and exhausted CRM retries also trigger handoff. The original CRM stage remains visible for mapping or external-write verification. Resuming a thread does not repair its CRM log automatically or close/change the source case's status.

## Delivery and recovery

- One active handoff per conversation: follow-ups merge their reasons without generating repeated alerts. After the operator resumes, a later incoming message can create another handoff. An old CRM retry cannot reopen a completed handoff for the same message.
- Alert reservations persist before Gmail is called. A timeout or worker crash after reservation leaves delivery uncertain; no automatic resend is attempted. **Verify Gmail notification** checks the authorized mailbox's Sent records using the stable message ID. Without sent proof, the alert remains held for human inspection.
- Failures before reservation retry with bounded backoff. After checking the Google connection/escalation contact, **Retry notification** can queue a confirmed unattempted notification. Changing the escalation address does not silently redirect an existing pending alert; explicit retry adopts the current contact.
- Notifications default to 20 attempts per hour per workspace (`HUMAN_ALERT_HOURLY_LIMIT`). Excess work defers to the next window without consuming its retry budget. This limits bursts; it is not an instant-notification guarantee.
- Pausing customer processing still lets pending human alerts and confirmed-delivery CRM jobs finish. A disconnected Google connector, changed mailbox or purged message prevents notification. Stopping the worker stops background work.

The additive `human_handoffs` table is created at application startup in both company and personal test schemas. Preserve the existing database and connector encryption key during deployment. No existing message/source data is replaced by this update.

## Supported scope and validation

Business profiles, policies and knowledge are configurable per installation. The current supported connectors are Gmail/Drive, Gemini, Salesforce and NetSuite. Custom CRM schemas, other helpdesks and additional languages require explicit extensions; use one installation per company. This is not shared multi-tenant hosting or a replacement for enterprise SSO.

Automated checks use controlled external adapters. The PostgreSQL pipeline test exercises real transactions, worker execution, concurrent delivery and CRM recovery with simulated Gmail/model/CRM responses. Before using an actual mailbox, verify Google consent, receipt, one agent notification, CRM permissions, case matching and your business's answer quality. Free Render instances sleep and cannot provide continuous unattended support. See [validation](VALIDATION.md) for the exact checks performed.
