import React from "react";
import DcInventory from "./dc-inventory/DcInventory.jsx";
import DeviceVisualization from "./device-visualization/DeviceVisualization.jsx";
import DhcpGenerator from "./dhcp-generator/DhcpGenerator.jsx";
import DeviceIcon from "./device-visualization/DeviceIcon.jsx";
import SubnetSplitter from "./subnet-splitter/SubnetSplitter.jsx";
import ConnectionTest from "./connection-test/ConnectionTest.jsx";
import RoutingMap from "./routing-map/RoutingMap.jsx";
import IpCalculator from "./ip-calculator/IpCalculator.jsx";
import Ipam from "./ipam/Ipam.jsx";
import Troubleshoot from "./troubleshoot/Troubleshoot.jsx";
import PostChangeValidation from "./post-change-validation/PostChangeValidation.jsx";

// To add a new tool:
//   1. Create src/tools/<your-tool>/YourTool.jsx (+ its own .css / logic.js if needed)
//   2. Import it below
//   3. Add an entry to this array — the toolbar and home page pick it up automatically
export const TOOLS = [
  {id:"dc-inventory",name:"DC Inventory",icon:React.createElement("svg",{width:20,height:20,viewBox:"0 0 20 20",fill:"none","aria-hidden":true},React.createElement("path",{d:"M4 2h12v16H4V2Zm0 5h12M4 12h12M7 4h1m-1 5h1m-1 5h1",stroke:"currentColor",strokeWidth:1.5})),tagline:"Place devices in data centers and configurable racks with U-level occupancy.",status:"live",Component:DcInventory},
  { id: "dhcp-generator", name: "DHCP Generator", icon: React.createElement("svg", { width: 20, height: 20, viewBox: "0 0 20 20", fill: "none", "aria-hidden": true }, React.createElement("path", { d: "M4 2h9l3 3v13H4V2Zm8 0v4h4M7 10h6M7 14h6", stroke: "currentColor", strokeWidth: 1.5 })), tagline: "Generate Check Point Gaia DHCP configuration with immutable version history.", status: "live", Component: DhcpGenerator },
  { id: "device-visualization", name: "Device Visualization", icon: React.createElement(DeviceIcon), tagline: "Map physical ports on switches, firewalls and servers.", status: "live", Component: DeviceVisualization },
  {
    id: "subnet-splitter",
    scope: "global",
    name: "Subnet Splitter",
    icon: "/⊃",
    tagline: "Carve a network into the largest CIDR blocks around excluded ranges.",
    status: "live",
    Component: SubnetSplitter,
  },
  {
    id: "connection-test",
    name: "Connection Test",
    icon: "⇄",
    tagline: "SSH/WinRM into source servers and test TCP connectivity to destinations.",
    status: "live",
    Component: ConnectionTest,
  },
  {
    id: "routing-map",
    name: "Routing Map",
    icon: "→",
    tagline: "Browse each host's routing table by network and next hop.",
    status: "live",
    Component: RoutingMap,
  },
  {
    id: "ip-calculator",
    scope: "global",
    name: "IP Calculator",
    icon: "#",
    tagline: "Enter an IP and netmask to get the network, broadcast, and usable host range.",
    status: "live",
    Component: IpCalculator,
  },
  {
    id: "ipam",
    name: "IPAM",
    icon: "▣",
    tagline: "Track subnets with a VLAN tag and record used, free, and reserved IP addresses.",
    status: "live",
    Component: Ipam,
  },
  {
    id: "troubleshoot",
    name: "Troubleshoot",
    icon: "◈",
    tagline: "Look up a device on the network and check its health.",
    status: "live",
    Component: Troubleshoot,
  },
  {
    id: "post-change-validation",
    name: "Post-Change Validation",
    icon: "✓",
    tagline: "Automated baseline capture, T-01 to T-22 post-change verification, and PIR generation.",
    status: "live",
    Component: PostChangeValidation,
  },
];

// True if `permissions` (a user's role.permissions list) grants access to
// toolId. "*" is the sentinel the "admin" role's permissions always carry,
// meaning unrestricted access — see server/auth_db.py's ADMIN_ROLE_NAME.
export function hasToolAccess(permissions, toolId) {
  if (!permissions) return false;
  return permissions.includes("*") || permissions.includes(toolId) ||
    (toolId === "ipam" && permissions.includes("ipam.read"));
}

// Live tools a given user is allowed to see, given their role permissions.
// When login isn't required there's no user/role to check against, so
// everything stays visible — matches the app's existing "open" behavior.
export function visibleTools(user, loginRequired) {
  if (!user) return loginRequired ? [] : TOOLS;
  return TOOLS.filter((tool) => hasToolAccess(tool.scope === "global" ? (user.globalPermissions || user.permissions) : user.permissions, tool.id));
}
