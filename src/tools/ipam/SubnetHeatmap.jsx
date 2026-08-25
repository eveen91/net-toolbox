import React, { useState } from "react";

const MAX_HEATMAP_ADDRESSES = 1024;

function ipToOffset(ip, subnetCidr) {
  const subnetBase = subnetCidr.split("/")[0];
  const subnetOctets = subnetBase.split(".").map(Number);
  const ipOctets = ip.split(".").map(Number);
  return ipOctets[3] + (ipOctets[2] - subnetOctets[2]) * 256;
}

export default function SubnetHeatmap({ subnet, subnets = [], onCellClick }) {
  const [hoveredCell, setHoveredCell] = useState(null);

  const totalAddresses = Math.min(subnet.totalAddresses || 0, MAX_HEATMAP_ADDRESSES);
  const subnetPrefix = parseInt(subnet.cidr.split("/")[1]);

  const existingAddresses = new Map();
  for (const addr of subnet.addresses || []) {
    existingAddresses.set(addr.address, addr);
  }

  const subnetPools = subnet.dhcpPools || [];

  // Find nested child subnets
  const childSubnets = [];
  if (subnets && subnets.length > 0) {
    for (const s of subnets) {
      if (s.id !== subnet.id) {
        const childPrefix = parseInt(s.cidr.split("/")[1]);
        if (childPrefix > subnetPrefix) {
          const childOffset = ipToOffset(s.cidr.split("/")[0], subnet.cidr);
          const childSize = Math.pow(2, 32 - childPrefix) / 256;
          if (childOffset >= 0 && childOffset + childSize <= totalAddresses) {
            childSubnets.push({
              ...s,
              startOffset: Math.floor(childOffset),
              endOffset: Math.ceil(childOffset + childSize - 1),
            });
          }
        }
      }
    }
  }

  // Build cells
  const cells = [];
  for (let i = 0; i < totalAddresses; i++) {
    const base = subnet.cidr.split("/")[0];
    const octets = base.split(".").map(Number);
    const lastOctet = octets[3] + i;
    const currentOctet = lastOctet > 255 ? lastOctet % 256 : lastOctet;
    const offsetIp = `${octets[0]}.${octets[1]}.${octets[2]}.${currentOctet}`;

    let status = "free";
    let className = "ip-heatmap-cell ip-heatmap-free";
    let isChildSubnet = false;
    let isDhcpPool = false;

    for (const cs of childSubnets) {
      if (i >= cs.startOffset && i <= cs.endOffset) {
        status = "child-subnet";
        className = "ip-heatmap-cell ip-heatmap-child";
        isChildSubnet = true;
        break;
      }
    }

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
      hostname: existingAddresses.has(offsetIp) ? existingAddresses.get(offsetIp)?.hostname : null,
      description: existingAddresses.has(offsetIp) ? existingAddresses.get(offsetIp)?.description : null,
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

  // Get cell count for child subnets
  const getChildCellCount = (cs) => {
    return cs.endOffset - cs.startOffset + 1;
  };

  // Get cell count for DHCP pools
  const getDhcpCellCount = (p) => {
    const poolStart = ipToOffset(p.start_ip, subnet.cidr);
    const poolEnd = ipToOffset(p.end_ip, subnet.cidr);
    return poolEnd - poolStart + 1;
  };

  return (
    <div className="ip-heatmap-container">
      {/* Child subnet outlines */}
      {childSubnets.map((cs) => (
        <div key={`child-${cs.id}`} className="ip-heatmap-child-outline">
          <div className="ip-heatmap-child-label" title={`${cs.cidr} ${cs.vlan ? `(VLAN ${cs.vlan})` : ""} ${cs.description ? `— ${cs.description}` : ""}`}>
            {cs.cidr}
          </div>
        </div>
      ))}

      {/* DHCP pool as single block */}
      {subnetPools.map((p) => {
        const cellCount = getDhcpCellCount(p);
        return (
          <div key={`pool-${p.id}`} className="ip-heatmap-dhcp-block">
            <div className="ip-heatmap-dhcp-label" title={`${p.name || "DHCP Pool"}: ${p.start_ip} – ${p.end_ip} ${p.description ? `— ${p.description}` : ""}`}>
              {p.name || "DHCP"}
            </div>
          </div>
        );
      })}

      {/* Individual IP cells */}
      {cells.filter((c) => !c.isChildSubnet && !c.isDhcpPool).map((cell) => (
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
