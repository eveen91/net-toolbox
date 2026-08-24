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
  {
    id: "subnet-splitter",
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
  return permissions.includes("*") || permissions.includes(toolId);
}

// Live tools a given user is allowed to see, given their role permissions.
// When login isn't required there's no user/role to check against, so
// everything stays visible — matches the app's existing "open" behavior.
export function visibleTools(user, loginRequired) {
  if (!loginRequired || !user) return TOOLS;
  return TOOLS.filter((tool) => hasToolAccess(user.permissions, tool.id));
}