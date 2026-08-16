import React, { useState } from "react";
import { changePassword } from "./api.js";

export default function ChangePasswordForm({ onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
    } catch (e2) {
      setError(e2.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="nt-change-password-panel">
      {success ? (
        <>
          <div className="tool-hint">Password changed.</div>
          <button className="tool-btn tool-btn-ghost" onClick={onClose}>
            Close
          </button>
        </>
      ) : (
        <form onSubmit={submit}>
          <input
            className="tool-input"
            type="password"
            placeholder="Current password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
          <input
            className="tool-input"
            type="password"
            placeholder="New password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          {error && <div className="tool-error">{error}</div>}
          <div className="nt-change-password-actions">
            <button
              className="tool-btn tool-btn-primary"
              type="submit"
              disabled={submitting || !currentPassword || !newPassword}
            >
              {submitting ? "Saving…" : "Save"}
            </button>
            <button className="tool-btn tool-btn-ghost" type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}