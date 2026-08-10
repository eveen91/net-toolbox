import SubnetSplitter from "./subnet-splitter/SubnetSplitter.jsx";
import ConnectionTest from "./connection-test/ConnectionTest.jsx";
import RoutingMap from "./routing-map/RoutingMap.jsx";
import IpCalculator from "./ip-calculator/IpCalculator.jsx";
import Ipam from "./ipam/Ipam.jsx";

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
];