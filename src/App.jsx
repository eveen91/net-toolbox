import "./tenants/tenants.css";
import React, { useState, useEffect, useRef } from "react";
import { canLeaveWorkspace, pageFromHash } from "./components/navigation.js";
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
  const [active, setActive] = useState(() => pageFromHash(window.location.hash));
  const activeRef = useRef(active);
  activeRef.current = active;
  const navigate = (id) => {
    if (id === activeRef.current) return;
    window.history.pushState(null, "", `#/${id}`);
    setActive(id);
  };
  useEffect(() => {
    const readLocation = () => {
      const id = pageFromHash(window.location.hash);
      if (id === activeRef.current) return;
      if (!canLeaveWorkspace()) { window.history.replaceState(null, "", `#/${activeRef.current}`); return; }
      setActive(id);
    };
    window.addEventListener("popstate", readLocation);
    window.addEventListener("hashchange", readLocation);
    return () => { window.removeEventListener("popstate", readLocation); window.removeEventListener("hashchange", readLocation); };
  }, []);
  const { loading, loginRequired, user, sessionExpired, refresh, tenantId, tenantSwitchError } = useAuth();

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
    refresh().catch(() => {});
  }, [active, refresh]);

  // Only tools the current role has access to — a tool id left over in
  // `active` (e.g. permissions were narrowed while this tab was open)
  // simply won't be found below, so it falls through to the "not found"
  // case rather than rendering.
  const tools = visibleTools(user, loginRequired);
  const activeTool = tools.find((t) => t.id === active);
  const canAccessAdmin = user?.role === "admin" || user?.tenantRole === "tenant-admin" || !loginRequired;

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

  useEffect(() => {
    if (loading || (loginRequired && !user)) return;
    document.title = `${effectiveActive === "home" ? "Workspace" : effectiveActive === "admin" ? "Administration" : activeTool?.name || "Workspace"} · net::toolbox`;
    const frame = requestAnimationFrame(() => document.getElementById("nt-main")?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [effectiveActive, activeTool?.name, loading, loginRequired, user?.id, tenantId]);

  if (loading) {
    return <div className="nt-auth-loading">Loading…</div>;
  }

  return (
    <>
      {loginRequired && !user ? (
        <LoginPage />
      ) : (
        <div>
          <a className="nt-skip-link" href="#nt-main" onClick={(event) => { event.preventDefault(); document.getElementById("nt-main")?.focus(); }}>Skip to content</a>
          <Toolbar active={effectiveActive} onNavigate={navigate} />

          <main id="nt-main" tabIndex={-1} className="nt-main" key={`${user?.id || "anonymous"}:${tenantId || "none"}`}>
            {tenantSwitchError ? <div className="tool-error" role="alert">{tenantSwitchError}
              <button className="tool-btn" onClick={() => refresh().catch(() => {})}>Retry</button>
            </div> : null}
            {effectiveActive === "home" && <HomePage onOpen={navigate} />}

            {!tenantSwitchError && effectiveActive !== "home" && activeTool && activeTool.Component && (
              <>
                <ErrorBoundary resetKey={effectiveActive}>
                  <activeTool.Component />
                </ErrorBoundary>
              </>
            )}

            {effectiveActive === "admin" && canAccessAdmin && (
              <>
                <ErrorBoundary resetKey={effectiveActive}>
                  <AdminGate />
                </ErrorBoundary>
              </>
            )}
          </main>
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
