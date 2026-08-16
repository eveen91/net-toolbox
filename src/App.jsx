import React, { useState } from "react";
import Toolbar from "./components/Toolbar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import HomePage from "./pages/HomePage.jsx";
import { TOOLS } from "./tools/registry.js";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import LoginPage from "./auth/LoginPage.jsx";
import SessionExpiredModal from "./auth/SessionExpiredModal.jsx";
import AdminPanel from "./admin/AdminPanel.jsx";
import "./tools/shared.css";

function AppShell() {
  const [active, setActive] = useState("home");
  const { loading, loginRequired, user, sessionExpired } = useAuth();
  const activeTool = TOOLS.find((t) => t.id === active);

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