import { apiFetch } from "../../apiFetch.js";

export async function listDevices() {
  const res = await apiFetch("/api/devices");
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function addDevice(device) {
  const res = await apiFetch("/api/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(device),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function updateDevice(id, device) {
  const res = await apiFetch(`/api/devices/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(device),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function deleteDevice(id) {
  const res = await apiFetch(`/api/devices/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function locateDevice(ip, username, password) {
  const res = await apiFetch("/api/troubleshoot/locate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function portHealth(deviceName, port, username, password) {
  const res = await apiFetch("/api/troubleshoot/port-health", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deviceName, port, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function runCableTest(deviceName, port, username, password, confirm) {
  const res = await apiFetch("/api/troubleshoot/cable-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deviceName, port, username, password, confirm }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function checkTransceiverHealth(deviceName, port, username, password) {
  const res = await apiFetch("/api/troubleshoot/transceiver-health", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deviceName, port, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function getStpReport(username, password) {
  const res = await apiFetch("/api/troubleshoot/stp-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function checkAccessStatus(deviceName, port, username, password) {
  const res = await apiFetch("/api/troubleshoot/access-check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deviceName, port, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function pingHost(ip) {
  const res = await apiFetch("/api/troubleshoot/ping", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function checkRoute(ip, username, password) {
  const res = await apiFetch("/api/troubleshoot/route-check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function runFullDiagnostic(ip, username, password) {
  const res = await apiFetch("/api/troubleshoot/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip, username, password }),
  });
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}

export async function getAuditLog() {
  const res = await apiFetch("/api/troubleshoot/audit-log");
  if (!res.ok) {
    throw new Error(`Backend error (${res.status})`);
  }
  return res.json();
}
