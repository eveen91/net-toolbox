import React, { useState } from "react";
import { saveBaseline } from "./api";

export default function BaselineTab({ plan, onBaselineSaved }) {
  const [ticketNumber, setTicketNumber] = useState(plan?.change_ticket || "");
  const [rawText, setRawText] = useState("");
  const [device, setDevice] = useState(plan?.target_devices?.[0] || "Core-VSX-01");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!ticketNumber.trim()) {
      setMessage({ type: "error", text: "Ticket number is required." });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        plan_id: plan ? plan.id : 1,
        ticket_number: ticketNumber,
        raw_outputs: { [device]: rawText },
        parsed_metrics: {},
      };
      const res = await saveBaseline(payload);
      setMessage({ type: "success", text: `Baseline saved with ID: ${res.id}` });
      if (onBaselineSaved) onBaselineSaved(res.id);
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="tool-section-title">Pre-Change Baseline Capture</div>
      <p className="tool-hint" style={{ marginBottom: "20px" }}>
        Capture or paste raw pre-change CLI output for target devices to enable automated post-change diffing.
      </p>

      {message && (
        <div className="tool-error" style={{ borderColor: message.type === "success" ? "#166534" : "#6b2c3a", backgroundColor: message.type === "success" ? "#dcfce7" : "#2a1420", color: message.type === "success" ? "#166534" : undefined }}>
          {message.text}
        </div>
      )}

      <form onSubmit={handleSave}>
        <div className="tool-field">
          <label className="tool-label">Change Ticket #</label>
          <input
            type="text"
            className="tool-input"
            value={ticketNumber}
            onChange={(e) => setTicketNumber(e.target.value)}
            placeholder="e.g. CHG0012345"
            required
          />
        </div>

        <div className="tool-field">
          <label className="tool-label">Target Device</label>
          <input
            type="text"
            className="tool-input"
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            placeholder="e.g. Core-VSX-01"
            required
          />
        </div>

        <div className="tool-field">
          <label className="tool-label">Raw Pre-Change Output</label>
          <textarea
            className="tool-textarea"
            style={{ height: "180px" }}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste show version, cphaprob stat, show interface brief, etc."
          />
        </div>

        <div className="tool-actions">
          <button type="submit" className="tool-btn tool-btn-primary" disabled={saving}>
            {saving ? "Saving Baseline..." : "Save Baseline Snapshot"}
          </button>
        </div>
      </form>
    </div>
  );
}
