import React, { useState } from "react";
import { bootstrapAdmin } from "./api.js";
import "../auth/auth.css";

export default function CreateAdminForm({ secretRequired, onCreated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setSubmitting(true);
    try {
      await bootstrapAdmin(username.trim(), password, secretRequired ? secret : null);
      await onCreated();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="nt-login-page">
      <form className="nt-login-form" onSubmit={submit}>
        <h1>net::toolbox</h1>
        <p className="tool-hint">
          No admin account exists yet. Create one to unlock the Config Panel.
        </p>
        <input
          className="tool-input"
          placeholder="Admin username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        {secretRequired && (
          <input
            className="tool-input"
            type="password"
            placeholder="Bootstrap secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        )}
        <input
          className="tool-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <input
          className="tool-input"
          type="password"
          placeholder="Confirm password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
        {error && <div className="tool-error">{error}</div>}
        <button
          className="tool-btn tool-btn-primary"
          type="submit"
          disabled={submitting || !username.trim() || !password || !confirmPassword || (secretRequired && !secret)}
        >
          {submitting ? "Creating…" : "Create admin account"}
        </button>
      </form>
    </div>
  );
}
