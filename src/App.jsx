import React, { useState } from "react";
import Toolbar from "./components/Toolbar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import HomePage from "./pages/HomePage.jsx";
import { visibleTools } from "./tools/registry.js";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import LoginPage from "./auth/LoginPage.jsx";
import SessionExpiredModal from "./auth/SessionExpiredModal.jsx";
import AdminPanel from "./admin/AdminPanel.jsx";
import "./tools/shared.css";

function AppShell() {
  const [active, setActive] = useState("home");
  const { loading, loginRequired, user, sessionExpired } = useAuth();
  // Only tools the current role has access to — a tool id left over in
  // `active` (e.g. permissions were narrowed while this tab was open)
  // simply won't be found below, so it falls through to the "not found"
  // case rather than rendering.
  const activeTool = visibleTools(user, loginRequired).find((t) => t.id === active);

  if (loading) {
    return <div className="nt-auth-loading">Loading…</div>;
  }

  return (
    <>
      {loginRequired && !user ? (
        <LoginPage />
      ) : (
        <div>
          <Toolbar active={active} onNavigate={setActive} />

          <div className="nt-main">
            {active === "home" && <HomePage onOpen={setActive} />}

            {active !== "home" && activeTool && activeTool.Component && (
              <>
                <button className="nt-back" onClick={() => setActive("home")}>
                  ← All tools
                </button>
                <ErrorBoundary resetKey={active}>
                  <activeTool.Component />
                </ErrorBoundary>
              </>
            )}

            {active === "admin" && (
              <>
                <button className="nt-back" onClick={() => setActive("home")}>
                  ← All tools
                </button>
                <ErrorBoundary resetKey={active}>
                  <AdminPanel />
                </ErrorBoundary>
              </>
            )}
          </div>
        </div>
      )}

      {sessionExpired && <SessionExpiredModal />}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}