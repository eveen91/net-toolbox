import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import { getBootstrapStatus } from "./api.js";
import AdminPanel from "./AdminPanel.jsx";
import AdminLoginForm from "./AdminLoginForm.jsx";
import CreateAdminForm from "./CreateAdminForm.jsx";

// Wraps AdminPanel with its own access gate, independent of the site-wide
// "require login" toggle:
//   - Login is required site-wide -> App.jsx only reaches this component
//     once `user` is a signed-in admin, so just render the panel.
//   - Login is NOT required site-wide (regular tools stay open) -> the
//     Config Panel still needs its own gate:
//       - no admin user exists yet  -> show the create-admin form
//       - an admin exists but this browser isn't signed in as one
//                                    -> show an admin-only login form
//       - signed in as admin        -> show the panel
export default function AdminGate() {
  const { user, loginRequired, refresh } = useAuth();
  const [adminExists, setAdminExists] = useState(null);
  const [error, setError] = useState(null);

  const loadStatus = useCallback(async () => {
    try {
      const status = await getBootstrapStatus();
      setAdminExists(status.adminExists);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (loginRequired) return;
    loadStatus();
  }, [loginRequired, loadStatus]);

  if (loginRequired || user?.role === "admin") {
    return <AdminPanel />;
  }

  if (error) {
    return <div className="tool-error">{error}</div>;
  }

  if (adminExists === null) {
    return <div className="nt-auth-loading">Loading…</div>;
  }

  if (!adminExists) {
    return (
      <CreateAdminForm
        onCreated={async () => {
          await refresh();
          await loadStatus();
        }}
      />
    );
  }

  return <AdminLoginForm onLoggedIn={loadStatus} />;
}
