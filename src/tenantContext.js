// Selection is per browser tab; every request captures it when sent.
const KEY = "nt-tenant-v1";
let selectedTenant = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(KEY);

export function getTenantId() {
  return selectedTenant;
}

export function setTenantId(id) {
  selectedTenant = id || null;
  if (typeof sessionStorage !== "undefined") {
    if (selectedTenant) sessionStorage.setItem(KEY, selectedTenant);
    else sessionStorage.removeItem(KEY);
  }
}

// EventSource cannot send custom headers. This selector still undergoes the
// same server-side membership checks as X-Tenant-ID.
export function tenantStreamUrl(url) {
  if (!selectedTenant) return url;
  return `${url}${url.includes("?") ? "&" : "?"}tenant_id=${encodeURIComponent(selectedTenant)}`;
}
