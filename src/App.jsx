import React, { useState, useEffect } from "react";
import Toolbar from "./components/Toolbar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import HomePage from "./pages/HomePage.jsx";
import { visibleTools } from "./tools/registry.js";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import LoginPage from "./auth/LoginPage.jsx";
import SessionExpiredModal from "./auth/SessionExpiredModal.jsx";
import AdminGate from "./admin/AdminGate.jsx";
import "./tools/shared.css";

function AppShell() {
  const [active, setActive] = useState("home");
  const { loading, loginRequired, user, sessionExpired, refresh } = useAuth();

  // Some tools (e.g. Connection Test) make no backend call until the user
  // submits something, so nothing would ever notice a dead session just
  // from opening them — unlike IPAM, which happens to fetch its subnet
  // list the instant it mounts and so discovers a dead session right
  // away. Re-validating on every navigation makes that immediate-redirect
  // behavior consistent across every tool, not just ones that happen to
  // fetch data on mount. getSessionInfo() is a cheap, always-200 read, so
  // this is safe to call on every tool switch.
  useEffect(() => {
    if (active === "home") return;
    refresh();
  }, [active, refresh]);

  // Only tools the current role has access to — a tool id left over in
  // `active` (e.g. permissions were narrowed while this tab was open)
  // simply won't be found below, so it falls through to the "not found"
  // case rather than rendering.
  const tools = visibleTools(user, loginRequired);
  const activeTool = tools.find((t) => t.id === active);
  const canAccessAdmin = user?.role === "admin" || !loginRequired;

  // `active` is local state that survives a logout/login inside the same
  // tab (AppShell never unmounts — only `user` changes). Without this
  // check, someone who navigated to a restricted page (e.g. an admin
  // opening Config Panel) and then logs out and back in as a different,
  // less-privileged role would land right back on that restricted page —
  // which is exactly the bug this guards against. Recomputed on every
  // render (not via an effect) so there's no flash of the restricted
  // page, and so the gated component (e.g. AdminPanel) never mounts and
  // never fires its own now-unauthorized API calls.
  const isActiveAuthorized =
    active === "home" ||
    (active === "admin" ? canAccessAdmin : !!activeTool);
  const effectiveActive = isActiveAuthorized ? active : "home";

  if (loading) {
    return <div className="nt-auth-loading">Loading…</div>;
  }

  return (
    <>
      {loginRequired && !user ? (
        <LoginPage />
      ) : (
        <div>
          <Toolbar active={effectiveActive} onNavigate={setActive} />

          <div className="nt-main">
            {effectiveActive === "home" && <HomePage onOpen={setActive} />}

            {effectiveActive !== "home" && activeTool && activeTool.Component && (
              <>
                <button className="nt-back" onClick={() => setActive("home")}>
                  ← All tools
                </button>
                <ErrorBoundary resetKey={effectiveActive}>
                  <activeTool.Component />
                </ErrorBoundary>
              </>
            )}

            {effectiveActive === "admin" && canAccessAdmin && (
              <>
                <button className="nt-back" onClick={() => setActive("home")}>
                  ← All tools
                </button>
                <ErrorBoundary resetKey={effectiveActive}>
                  <AdminGate />
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