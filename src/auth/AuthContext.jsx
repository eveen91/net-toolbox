import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { getSessionInfo, login as loginRequest, logout as logoutRequest } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [loginRequired, setLoginRequired] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const info = await getSessionInfo();
      setLoginRequired(info.loginRequired);
      setUser(info.user);
    } catch (e) {
      console.error("Failed to load session info", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const handler = () => {
      setSessionExpired(true);
      refresh();
    };
    window.addEventListener("nt-auth-required", handler);
    return () => window.removeEventListener("nt-auth-required", handler);
  }, [refresh]);

  const login = async (username, password) => {
    const loggedInUser = await loginRequest(username, password);
    setUser(loggedInUser);
    setSessionExpired(false);
    return loggedInUser;
  };

  const logout = async () => {
    await logoutRequest();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ loginRequired, user, loading, login, logout, refresh, sessionExpired }}>
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