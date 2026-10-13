import { apiFetch } from "../apiFetch.js";
const BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function tenantRequest(path = "", options = {}) {
  const response = await apiFetch(`${BASE}/api/tenants${path}`, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not update tenant access");
  return body;
}

export function createTenant(name) {
  return tenantRequest("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
}

export function setMember(tenantId, userId, role) {
  return tenantRequest(`/${encodeURIComponent(tenantId)}/members/${userId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }),
  });
}

export function removeMember(tenantId, userId) {
  return tenantRequest(`/${encodeURIComponent(tenantId)}/members/${userId}`, { method: "DELETE" });
}
