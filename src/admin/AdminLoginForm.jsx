import React, { useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import "../auth/auth.css";

export default function AdminLoginForm({ onLoggedIn }) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const loggedInUser = await login(username, password);
      if (loggedInUser.role !== "admin") {
        setError("This account does not have Config Panel access.");
        return;
      }
      await onLoggedIn();
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
        <p className="tool-hint">Sign in as an admin to open the Config Panel</p>
        <input
          className="tool-input"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <input
          className="tool-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="tool-error">{error}</div>}
        <button
          className="tool-btn tool-btn-primary"
          type="submit"
          disabled={submitting || !username.trim() || !password}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
