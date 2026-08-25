import React, { useState } from "react";

const MAX_HEATMAP_ADDRESSES = 1024; // /22 = 1024 IPs, /21 = 2048, cap at /22

function ipToOffset(ip, subnetCidr) {
  const subnetBase = subnetCidr.split("/")[0];
  const subnetPrefix = parseInt(subnetCidr.split("/")[1]);
  const subnetOctets = subnetBase.split(".").map(Number);
  const ipOctets = ip.split(".").map(Number);
  
  // Calculate offset within the subnet
  return ipOctets[3] + (ipOctets[2] - subnetOctets[2]) * 256 + 
         (ipOctets[1] - subnetOctets[1]) * 65536 + 
         (ipOctets[0] - subnetOctets[0]) * 16777216;
}

export default function SubnetHeatmap({ subnet, subnets = [], pools = [], onCellClick }) {
  const [hoveredCell, setHoveredCell] = useState(null);

  // Calculate total host capacity (capped at 1024)
  const totalAddresses = Math.min(subnet.totalAddresses || 0, MAX_HEATMAP_ADDRESSES);

  // Build a set of addresses that exist in this subnet
  const existingAddresses = new Map();
  for (const addr of subnet.addresses || []) {
    existingAddresses.set(addr.address, addr);
  }

  // Find nested child subnets that fit in this subnet
  const childSubnets = [];
  if (subnets && subnets.length > 0) {
    const net = subnet.cidr.split("/")[0];
    const prefix = parseInt(subnet.cidr.split("/")[1]);
    for (const s of subnets) {
      if (s.id !== subnet.id) {
        const childNet = s.cidr.split("/")[0];
        const childPrefix = parseInt(s.cidr.split("/")[1]);
        // Check if child is nested within this subnet
        if (childPrefix > prefix) {
          const childOffset = ipToOffset(childNet, subnet.cidr);
          const childSize = Math.pow(2, 32 - childPrefix);
          if (childOffset >= 0 && childOffset + childSize <= totalAddresses) {
            childSubnets.push({
              ...s,
              startOffset: childOffset,
              endOffset: childOffset + childSize - 1,
            });
          }
        }
      }
    }
  }

  // Find DHCP pools in this subnet
  const subnetPools = pools.filter((p) => p.subnet_id === subnet.id);

  // Build the grid cells
  const cells = [];
  for (let i = 0; i < totalAddresses; i++) {
    // Get the IP at this offset
    const base = subnet.cidr.split("/")[0];
    const octets = base.split(".").map(Number);
    const lastOctet = octets[3] + i;

    // Handle overflow across octets
    let currentOctet = lastOctet;
    if (currentOctet > 255) {
      currentOctet = currentOctet % 256;
    }
    const offsetIp = `${octets[0]}.${octets[1]}.${octets[2]}.${currentOctet}`;

    // Determine cell status
    let status = "free";
    let className = "ip-heatmap-cell ip-heatmap-free";
    let isChildSubnet = false;
    let isDhcpPool = false;

    // Check if this cell is in a child subnet
    for (const cs of childSubnets) {
      if (i >= cs.startOffset && i <= cs.endOffset) {
        status = "child-subnet";
        className = "ip-heatmap-cell ip-heatmap-child";
        isChildSubnet = true;
        break;
      }
    }

    // Check if this cell is in a DHCP pool
    if (!isChildSubnet) {
      for (const p of subnetPools) {
        const poolStart = ipToOffset(p.start_ip, subnet.cidr);
        const poolEnd = ipToOffset(p.end_ip, subnet.cidr);
        if (i >= poolStart && i <= poolEnd) {
          status = "dhcp-pool";
          className = "ip-heatmap-cell ip-heatmap-dhcp";
          isDhcpPool = true;
          break;
        }
      }
    }

    // Check if this cell has a recorded address
    if (!isChildSubnet && !isDhcpPool) {
      const addr = existingAddresses.get(offsetIp);
      if (addr) {
        if (addr.status === "used") {
          status = "used";
          className = "ip-heatmap-cell ip-heatmap-used";
        } else if (addr.status === "reserved") {
          status = "reserved";
          className = "ip-heatmap-cell ip-heatmap-reserved";
        }
      }
    }

    cells.push({
      key: i,
      ip: offsetIp,
      status,
      className,
      hostname: existingAddresses.has(offsetIp)
        ? existingAddresses.get(offsetIp)?.hostname
        : null,
      description: existingAddresses.has(offsetIp)
        ? existingAddresses.get(offsetIp)?.description
        : null,
      isChildSubnet,
      isDhcpPool,
    });
  }

  if (totalAddresses > MAX_HEATMAP_ADDRESSES) {
    return (
      <div className="tool-warning">
        Heatmap disabled for broad prefixes (>1024 IPs). We recommend carving this block into nested subnets using the Subnet Splitter tool.
      </div>
    );
  }

  return (
    <div className="ip-heatmap-container">
      {/* Child subnet labels */}
      {childSubnets.map((cs, idx) => {
        const labelStart = cs.startOffset;
        const labelEnd = cs.endOffset;
        const labelWidth = labelEnd - labelStart + 1;
        return (
          <div
            key={`child-${cs.id}`}
            className="ip-heatmap-child-label"
            style={{
              gridColumn: `span ${Math.max(labelWidth, 1)}`,
              gridColumnStart: labelStart + 1,
            }}
            title={`${cs.cidr} ${cs.vlan ? `(VLAN ${cs.vlan})` : ""} ${cs.description ? `— ${cs.description}` : ""}`}
          >
            {cs.cidr}
          </div>
        );
      })}

      {/* DHCP pool labels */}
      {subnetPools.map((p, idx) => {
        const poolStart = ipToOffset(p.start_ip, subnet.cidr);
        const poolEnd = ipToOffset(p.end_ip, subnet.cidr);
        const poolWidth = poolEnd - poolStart + 1;
        return (
          <div
            key={`pool-${p.id}`}
            className="ip-heatmap-dhcp-label"
            style={{
              gridColumn: `span ${Math.max(poolWidth, 1)}`,
              gridColumnStart: poolStart + 1,
            }}
            title={`${p.name || "DHCP Pool"}: ${p.start_ip} – ${p.end_ip} ${p.description ? `— ${p.description}` : ""}`}
          >
            {p.name || "DHCP"}
          </div>
        );
      })}

      {/* IP cells */}
      {cells.map((cell) => (
        <div
          key={cell.key}
          className={cell.className}
          onMouseEnter={() => setHoveredCell(cell)}
          onMouseLeave={() => setHoveredCell(null)}
          onClick={() => onCellClick?.(cell.ip)}
          title={cell.hostname ? `${cell.ip} - ${cell.hostname}` : cell.ip}
        >
          {hoveredCell?.key === cell.key && (
            <div className="ip-heatmap-tooltip">
              <div className="ip-heatmap-tooltip-ip">{cell.ip}</div>
              <div className="ip-heatmap-tooltip-status">{cell.status}</div>
              {cell.hostname && <div className="ip-heatmap-tooltip-hostname">{cell.hostname}</div>}
              {cell.description && <div className="ip-heatmap-tooltip-description">{cell.description}</div>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
