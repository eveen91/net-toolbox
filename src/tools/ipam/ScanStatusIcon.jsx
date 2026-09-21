import React from "react";
import { scanAddressLabel, useActiveIpamScan } from "./hooks/useIpamScan.js";

export default function ScanStatusIcon({ subnetId }) {
  const { scanning, addresses } = useActiveIpamScan(subnetId);

  return (
    <span className="ip-scan-status-icon-wrap">
      <span
        className={`ip-scan-status-icon ${scanning ? "scanning" : "idle"}`}
        aria-label={scanning ? "Scan in progress" : "Scan idle"}
      />
      {addresses.length > 0 && (
        <div className="ip-scan-status-popover">
          <div className="tool-hint">{scanning ? "Scan in progress" : "Last scan"}</div>
          <div className="ip-scan-status-list">
            {addresses.map((address) => (
              <div key={address.address} className="ip-scan-status-row">
                <span className="ip-scan-status-addr">{address.address}</span>
                <span className={`ip-scan-status-badge ${address.status}`}>
                  {scanAddressLabel(address)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}
