export const AUDIT_EVENT_TYPES = [
  "create",
  "update",
  "delete",
  "reassign",
  "subnet_create",
  "subnet_update",
  "subnet_delete",
  "dhcp_pool_create",
  "dhcp_pool_update",
  "dhcp_pool_delete",
  "dhcp_pool_move",
  "dhcp_pool_bulk_move",
  "tag_create",
  "tag_delete",
  "subnet_tag_add",
  "subnet_tag_remove",
  "address_tag_add",
  "address_tag_remove",
  "settings_update",
];

const AUDIT_EVENT_LABELS = {
  create: "Address created",
  update: "Address updated",
  delete: "Address deleted",
  reassign: "Address reassigned",
  subnet_create: "Subnet created",
  subnet_update: "Subnet updated",
  subnet_delete: "Subnet deleted",
  dhcp_pool_create: "DHCP pool created",
  dhcp_pool_update: "DHCP pool updated",
  dhcp_pool_delete: "DHCP pool deleted",
  dhcp_pool_move: "DHCP pool moved",
  dhcp_pool_bulk_move: "DHCP pools moved",
  tag_create: "Tag created",
  tag_delete: "Tag deleted",
  subnet_tag_add: "Subnet tag added",
  subnet_tag_remove: "Subnet tag removed",
  address_tag_add: "Address tag added",
  address_tag_remove: "Address tag removed",
  settings_update: "Settings updated",
};

export function auditEventLabel(changeType) {
  if (!changeType) return "Other change";
  return AUDIT_EVENT_LABELS[changeType] || changeType.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function auditEventTone(changeType) {
  if (changeType?.includes("delete") || changeType?.includes("remove")) return "danger";
  if (changeType?.includes("create") || changeType?.includes("add")) return "success";
  if (changeType?.includes("move") || changeType === "reassign") return "accent";
  if (changeType?.includes("update")) return "info";
  return "neutral";
}

export function auditDiffRows(oldValue, newValue) {
  const keys = new Set([
    ...Object.keys(oldValue || {}),
    ...Object.keys(newValue || {}),
  ]);
  return Array.from(keys).sort().map((field) => ({
    field,
    oldValue: oldValue?.[field],
    newValue: newValue?.[field],
  }));
}

export function formatAuditValue(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function buildAuditQueryParams({
  subnetId,
  addressId,
  startDate,
  endDate,
  changeTypes = [],
  limit,
  offset,
} = {}) {
  const params = new URLSearchParams();
  if (subnetId !== undefined && subnetId !== null && subnetId !== "") params.set("subnet_id", String(subnetId));
  if (addressId !== undefined && addressId !== null && addressId !== "") params.set("address_id", String(addressId));
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  for (const changeType of changeTypes) {
    if (changeType) params.append("change_type", changeType);
  }
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  return params;
}

export function auditPageCount(total, limit) {
  if (!total || !limit) return 1;
  return Math.max(1, Math.ceil(total / limit));
}
