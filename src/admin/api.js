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

export async function listUsers() {
  const res = await apiFetch(`${BASE_URL}/api/admin/users`);
  return handle(res);
}

export async function createUser(username, password, role) {
  const res = await apiFetch(`${BASE_URL}/api/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
  return handle(res);
}

export async function deleteUser(userId) {
  const res = await apiFetch(`${BASE_URL}/api/admin/users/${userId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function updateUserRole(userId, role) {
  const res = await apiFetch(`${BASE_URL}/api/admin/users/${userId}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  return handle(res);
}

export async function listRoles() {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles`);
  return handle(res);
}

export async function createRole(name, permissions) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, permissions }),
  });
  return handle(res);
}

export async function updateRole(roleId, permissions) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles/${roleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ permissions }),
  });
  return handle(res);
}

export async function deleteRole(roleId) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles/${roleId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function listRoleAdGroups(roleId) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles/${roleId}/ad-groups`);
  return handle(res);
}

export async function addRoleAdGroup(roleId, groupDn) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles/${roleId}/ad-groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groupDn }),
  });
  return handle(res);
}

export async function removeRoleAdGroup(roleId, groupDn) {
  const res = await apiFetch(`${BASE_URL}/api/admin/roles/${roleId}/ad-groups`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groupDn }),
  });
  return handle(res);
}

export async function resetPassword(userId, newPassword) {
  const res = await apiFetch(`${BASE_URL}/api/admin/users/${userId}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ newPassword }),
  });
  return handle(res);
}

export async function getBootstrapStatus() {
  const res = await apiFetch(`${BASE_URL}/api/admin/bootstrap-status`);
  return handle(res);
}

export async function bootstrapAdmin(username, password, secret = null) {
  const body = { username, password };
  if (secret) body.secret = secret;
  const res = await apiFetch(`${BASE_URL}/api/admin/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function setRequireLogin(enabled) {
  const res = await apiFetch(`${BASE_URL}/api/admin/settings/require-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return handle(res);
}

export async function getAdSettings() {
  const res = await apiFetch(`${BASE_URL}/api/admin/settings/ad`);
  return handle(res);
}

export async function updateAdSettings(settings) {
  const res = await apiFetch(`${BASE_URL}/api/admin/settings/ad`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  return handle(res);
}

export async function testAdConnection(overrides = {}) {
  const res = await apiFetch(`${BASE_URL}/api/admin/settings/ad/test-connection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
  });
  return handle(res);
}