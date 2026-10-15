export const TOOL_GROUPS = [
  { id: "infrastructure", label: "Infrastructure", tools: ["dc-inventory", "ipam", "dhcp-generator", "device-visualization", "routing-map"] },
  { id: "diagnostics", label: "Diagnostics", tools: ["troubleshoot", "connection-test", "post-change-validation"] },
  { id: "utilities", label: "Utilities", tools: ["ip-calculator", "subnet-splitter"] },
];

export function navigationGroups(tools) {
  return TOOL_GROUPS.map((group) => ({ ...group, items: group.tools.map((id) => tools.find((tool) => tool.id === id)).filter(Boolean) }))
    .filter((group) => group.items.length > 0);
}

export function pageFromHash(hash) {
  return hash.replace(/^#\/?/, "").split(/[/?]/)[0] || "home";
}

export function canLeaveWorkspace() {
  return typeof window === "undefined" || window.dispatchEvent(new Event("nt-before-navigate", { cancelable: true }));
}
