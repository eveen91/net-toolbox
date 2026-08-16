import { apiFetch } from "../apiFetch.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? String(body.detail) : detail;
    } catch {
      // ignore — keep statusText
    }
    throw new Error(`Backend error (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getSessionInfo() {
  const res = await apiFetch(`${BASE_URL}/api/auth/session`);
  return handle(res);
}

export async function login(username, password) {
  const res = await apiFetch(`${BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handle(res);
}

export async function logout() {
  const res = await apiFetch(`${BASE_URL}/api/auth/logout`, { method: "POST" });
  return handle(res);
}

export async function changePassword(currentPassword, newPassword) {
  const res = await apiFetch(`${BASE_URL}/api/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ currentPassword, newPassword }),
  });
  return handle(res);
}