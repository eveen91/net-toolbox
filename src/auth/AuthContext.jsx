import { setTenantId, getTenantId } from "../tenantContext.js";
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { getSessionInfo, login as loginRequest, logout as logoutRequest } from "./api.js";

const AuthContext = createContext(null);

// Tracks (outside React state, so it survives a full page reload) that this
// browser previously had a logged-in session. If a fresh page load finds
// this flag set but the backend reports no user, the most likely reason is
// that the session expired (or was invalidated) since the last time this
// tab was open — not that this is someone's first visit — so we can still
// show the "your session expired" message even though we never received a
// live 401 in this page's lifetime to trigger it the usual way.
const HAD_SESSION_KEY = "nt-had-session";

// Written synchronously (no await) the instant a 401 is detected, so it
// survives even if the page reloads before the async refresh() below gets
// a chance to run — localStorage.setItem is immediate, unlike a fetch.
// On the next refresh() — whether that's later in this same page's
// lifetime or after a fresh reload — we check this first and, if present,
// know for certain the expiry banner should show, then consume the flag.
const SESSION_EXPIRED_PENDING_KEY = "nt-session-expired-pending";

export function AuthProvider({ children }) {
  const [loginRequired, setLoginRequired] = useState(false);
  const [adEnabled, setAdEnabled] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [tenantId, setSelectedTenant] = useState(getTenantId);
  const [tenantSwitchError, setTenantSwitchError] = useState(null);
  const refreshSequence = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const info = await getSessionInfo();
      if (sequence !== refreshSequence.current) return;
      setTenantSwitchError(null);
      setTenants(info.tenants || []);
      setTenantId(info.tenantId);
      setSelectedTenant(info.tenantId || null);
      setLoginRequired(info.loginRequired);
      setAdEnabled(info.adEnabled);
      setUser(info.user);
      if (info.user) {
        localStorage.setItem(HAD_SESSION_KEY, "1");
      } else {
        if (localStorage.getItem(SESSION_EXPIRED_PENDING_KEY)) {
          setSessionExpired(true);
          localStorage.removeItem(SESSION_EXPIRED_PENDING_KEY);
        } else if (localStorage.getItem(HAD_SESSION_KEY)) {
          setSessionExpired(true);
        }
        localStorage.removeItem(HAD_SESSION_KEY);
      }
    } catch (e) {
      if (sequence !== refreshSequence.current) return;
      setTenantSwitchError("Could not verify tenant access. Please retry.");
      throw e;
    } finally {
      if (sequence === refreshSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    const handler = () => {
      setSessionExpired(true);
      localStorage.setItem(SESSION_EXPIRED_PENDING_KEY, "1");
      refresh().catch(() => {});
    };
    window.addEventListener("nt-auth-required", handler);
    return () => window.removeEventListener("nt-auth-required", handler);
  }, [refresh]);

  const login = async (username, password, authMethod = "local") => {
    const loggedInUser = await loginRequest(username, password, authMethod);
    setLoading(true);
    setSessionExpired(false);
    localStorage.setItem(HAD_SESSION_KEY, "1");
    localStorage.removeItem(SESSION_EXPIRED_PENDING_KEY);
    await refresh();
    return loggedInUser;
  };

  const logout = async () => {
    await logoutRequest();
    setUser(null);
    setTenantId(null);
    await refresh();
    localStorage.removeItem(HAD_SESSION_KEY);
    localStorage.removeItem(SESSION_EXPIRED_PENDING_KEY);
  };

  const switchTenant = async (id) => {
    if (!tenants.some((tenant) => tenant.id === id)) return;
    setLoading(true);
    setTenantSwitchError(null);
    setTenantId(id);
    await refresh().catch(() => {});
  };

  return (
    <AuthContext.Provider value={{ loginRequired, adEnabled, user, loading, login, logout, refresh, sessionExpired, tenants, tenantId, switchTenant, tenantSwitchError }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return ctx;
}