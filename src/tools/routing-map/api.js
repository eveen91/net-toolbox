// Talks to the same backend as Connection Test (server/main.py), which
// stores routing tables in SQLite (see server/db.py).

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

export async function listRoutingHosts() {
  const res = await fetch(`${BASE_URL}/api/routing/hosts`);
  return handle(res);
}

export async function exportRoutingHosts() {
  const res = await fetch(`${BASE_URL}/api/routing/export`);
  return handle(res);
}

export async function getRoutingHost(host) {
  const res = await fetch(`${BASE_URL}/api/routing/hosts/${encodeURIComponent(host)}`);
  return handle(res);
}

export async function saveRoutingHost(host, routes, interfaces = []) {
  const res = await fetch(`${BASE_URL}/api/routing/hosts/${encodeURIComponent(host)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routes, interfaces }),
  });
  return handle(res);
}

export async function deleteRoutingHost(host) {
  const res = await fetch(`${BASE_URL}/api/routing/hosts/${encodeURIComponent(host)}`, {
    method: "DELETE",
  });
  return handle(res);
}
