import { apiFetch } from "../../apiFetch.js";
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
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets`);
  return handle(res);
}

export async function getIpamDashboard() {
  const res = await apiFetch(`${BASE_URL}/api/ipam/dashboard`);
  return handle(res);
}

export async function getSubnet(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`);
  return handle(res);
}

export async function createSubnet(cidr, vlan, description) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr, vlan, description }),
  });
  return handle(res);
}

export async function updateSubnet(subnetId, cidr, vlan, description) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr, vlan, description }),
  });
  return handle(res);
}

export async function deleteSubnet(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}`, {
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
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses`, {
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
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}`, {
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
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function bulkUpdateAddresses(subnetId, addressIds, fields) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/bulk`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ addressIds, ...fields }),
  });
  return handle(res);
}

export async function bulkDeleteAddresses(subnetId, addressIds) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/bulk-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ addressIds }),
  });
  return handle(res);
}

export async function bulkMoveAddresses(subnetId, addressIds, targetSubnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/bulk-move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ addressIds, targetSubnetId }),
  });
  return handle(res);
}

export async function rescanAddress(subnetId, addressId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}/rescan`, {
    method: "POST",
  });
  return handle(res);
}

export async function autodiscoverSubnet(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover`, {
    method: "POST",
  });
  return handle(res);
}

export async function startAutodiscoverJob(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover/start`, {
    method: "POST",
  });
  return handle(res);
}

export function autodiscoverStreamUrl(subnetId, jobId) {
  return `${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover/stream/${jobId}`;
}

export async function getActiveAutodiscoverJob(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/autodiscover/active`);
  return handle(res);
}

export async function listSubnetScans(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scans`);
  return handle(res);
}

export async function listScanExcludes(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes`);
  return handle(res);
}

export async function addScanExclude(subnetId, address) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
  });
  return handle(res);
}

export async function removeScanExclude(subnetId, excludeId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/scan-excludes/${excludeId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function getIpamSettings() {
  const res = await apiFetch(`${BASE_URL}/api/ipam/settings`);
  return handle(res);
}

export async function updateIpamSettings(scanConcurrencyLimit) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scanConcurrencyLimit }),
  });
  return handle(res);
}

export async function getMisplacedAddresses() {
  const res = await apiFetch(`${BASE_URL}/api/ipam/misplaced-addresses`);
  return handle(res);
}

export async function moveAddress(subnetId, addressId, targetSubnetId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/subnets/${subnetId}/addresses/${addressId}/move`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetSubnetId }),
    }
  );
  return handle(res);
}

export async function searchAddresses(query) {
  if (!query || !query.trim()) return [];
  const res = await apiFetch(`${BASE_URL}/api/ipam/addresses/search?q=${encodeURIComponent(query.trim())}`);
  return handle(res);
}

export async function createDhcpPool(subnetId, data) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/dhcp-pools`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handle(res);
}

export async function updateDhcpPool(subnetId, poolId, data) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/dhcp-pools/${poolId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handle(res);
}

export async function getDhcpPools(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/dhcp-pools`);
  return handle(res);
}

export async function deleteDhcpPool(subnetId, poolId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/dhcp-pools/${poolId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function bulkMoveDhcpPools(poolIds, targetSubnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/dhcp-pools/bulk-move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ poolIds, targetSubnetId }),
  });
  return handle(res);
}

export async function getMisplacedDhcpPools() {
  const res = await apiFetch(`${BASE_URL}/api/ipam/misplaced-dhcp-pools`);
  return handle(res);
}

export async function getNextAvailableIp(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/next-available`);
  return handle(res);
}

export async function moveDhcpPool(subnetId, poolId, targetSubnetId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/subnets/${subnetId}/dhcp-pools/${poolId}/move`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targetSubnetId }),
    }
  );
  return handle(res);
}

// ---------------------------------------------------------------------------
// Custom Tags
// ---------------------------------------------------------------------------

export async function fetchTags() {
  const res = await apiFetch(`${BASE_URL}/api/ipam/tags`);
  const data = await handle(res);
  return data.tags;
}

export async function createTag(tagData) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tagData),
  });
  return handle(res);
}

export async function deleteTag(tagId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/tags/${tagId}`, {
    method: "DELETE",
  });
  return handle(res);
}

export async function searchTags(query) {
  if (!query || !query.trim()) return [];
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/tags/search?q=${encodeURIComponent(query.trim())}`
  );
  return handle(res);
}

export async function fetchSubnetTags(subnetId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/subnets/${subnetId}/tags`);
  return handle(res);
}

export async function addSubnetTag(subnetId, tagId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/subnets/${subnetId}/tags/${tagId}`,
    { method: "POST" }
  );
  return handle(res);
}

export async function removeSubnetTag(subnetId, tagId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/subnets/${subnetId}/tags/${tagId}`,
    { method: "DELETE" }
  );
  return handle(res);
}

export async function fetchAddressTags(addressId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/addresses/${addressId}/tags`);
  return handle(res);
}

export async function addAddressTag(addressId, tagId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/addresses/${addressId}/tags/${tagId}`,
    { method: "POST" }
  );
  return handle(res);
}

export async function removeAddressTag(addressId, tagId) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/addresses/${addressId}/tags/${tagId}`,
    { method: "DELETE" }
  );
  return handle(res);
}

export async function fetchSubnetsByTag(tagId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/tags/${tagId}/subnets`);
  return handle(res);
}

export async function fetchAddressesByTag(tagId) {
  const res = await apiFetch(`${BASE_URL}/api/ipam/tags/${tagId}/addresses`);
  return handle(res);
}

export async function fetchSubnetAllocation(parentCidr, prefix) {
  const res = await apiFetch(
    `${BASE_URL}/api/ipam/subnet-allocation?parent=${encodeURIComponent(parentCidr)}&prefix=${prefix}`,
  );
  return handle(res);
}
