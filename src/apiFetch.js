// Paths whose own 401 response means "these credentials are wrong" or
// otherwise doesn't imply a previously-valid session just died — as
// opposed to every other 401 in this app, which comes from the auth
// middleware rejecting an authenticated request and genuinely does mean
// the session expired. A failed login attempt must never trigger the
// "your session expired" flow.
const AUTH_401_EXEMPT_PATHS = ["/api/auth/login"];

export async function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  headers["X-CSRF-TOKEN"] = "fixed-csrf-token";
  options.headers = headers;

  const res = await fetch(url, { ...options, credentials: "include" });
  const isExempt = AUTH_401_EXEMPT_PATHS.some((path) => url.includes(path));
  if (res.status === 401 && !isExempt) {
    window.dispatchEvent(new CustomEvent("nt-auth-required"));
  }
  return res;
}