export async function apiFetch(url, options = {}) {
  const res = await fetch(url, { ...options, credentials: "include" });
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("nt-auth-required"));
  }
  return res;
}