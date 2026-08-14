// Talks to the same backend as Routing Map (server/main.py), which stores
// subnets and their recorded addresses in SQLite (see server/db.py).

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

export async function listSubnets() {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets`);
  return handle(res);
}

export async function getSubnet(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`);
  return handle(res);
}

export async function createSubnet(cidr, vlan, description) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr, vlan, description }),
  });
  return handle(res);
}

export async function updateSubnet(subnetId, cidr, vlan, description) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr, vlan, description }),
  });
  return handle(res);
}

export async function deleteSubnet(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function addAddress(
  subnetId,
  address,
  status,
  hostname,
  description,
  team,
  machineType,
  vmCluster,
  environment,
  locked
) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      address,
      status,
      hostname,
      description,
      team,
      machineType,
      vmCluster,
      environment,
      locked,
    }),
  });
  return handle(res);
}

export async function updateAddress(
  subnetId,
  addressId,
  address,
  status,
  hostname,
  description,
  team,
  machineType,
  vmCluster,
  environment,
  locked
) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      address,
      status,
      hostname,
      description,
      team,
      machineType,
      vmCluster,
      environment,
      locked,
    }),
  });
  return handle(res);
}

export async function deleteAddress(subnetId, addressId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function rescanAddress(subnetId, addressId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}/rescan`, {
    method: "POST",
  });
  return handle(res);
}

export async function autodiscoverSubnet(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover`, {
    method: "POST",
  });
  return handle(res);
}

export async function startAutodiscoverJob(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover/start`, {
    method: "POST",
  });
  return handle(res);
}

export function autodiscoverStreamUrl(subnetId, jobId) {
  return `${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover/stream/${jobId}`;
}

export async function listSubnetScans(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scans`);
  return handle(res);
}

export async function listScanExcludes(subnetId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes`);
  return handle(res);
}

export async function addScanExclude(subnetId, address) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
  });
  return handle(res);
}

export async function removeScanExclude(subnetId, excludeId) {
  const res = await fetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes/${excludeId}`, {
    method: "DELETE",
  });
  return handle(res);
}