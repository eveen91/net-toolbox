import { apiFetch } from "../../apiFetch.js";
// Talks to the Python backend (server/main.py) which does the actual
// SSH / WinRM work — the browser can't open those sessions itself.
//
// In dev, vite.config.js proxies /api -> http://localhost:8000.
// In production, put a reverse proxy in front that does the same, or set
// VITE_API_BASE_URL to the backend's full URL.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export async function runConnectionTest(payload) {
  const res = await apiFetch(`${BASE_URL}/api/connection-test/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map(item => {
        const field = (item.loc || []).filter(part => part !== "body").join(".");
        return `${field ? `${field}: ` : ""}${item.msg || "Invalid value"}`;
      }).join("; ");
    } catch {
      // ignore — keep statusText
    }
    throw new Error(`Backend error (${res.status}): ${detail}`);
  }

  return res.json();
}