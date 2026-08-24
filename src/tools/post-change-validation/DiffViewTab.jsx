import React from "react";

export default function DiffViewTab() {
  return (
    <div>
      <div className="tool-section-title">Baseline vs. Post-Change Visual Diff</div>
      <p className="tool-hint" style={{ marginBottom: "20px" }}>
        Parsed state delta highlighting changes, additions, and potential operational anomalies.
      </p>

      <div className="tool-error" style={{ borderColor: "#166534", backgroundColor: "#123a2e", color: "#6ee7b7", marginBottom: "20px" }}>
        Zero negative operational deltas detected across target interfaces and routing tables.
      </div>

      <div className="tool-table-wrap">
        <table className="tool-table">
          <thead>
            <tr>
              <th>Metric / Object</th>
              <th>Pre-Change State</th>
              <th>Post-Change State</th>
              <th>Delta Type</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>VLAN 200 Interface</td>
              <td>Non-existent</td>
              <td>Up / Operational</td>
              <td><span className="tool-pill tool-pill-ok">Added</span></td>
            </tr>
            <tr>
              <td>CP Cluster VIP (10.200.0.1)</td>
              <td>Unreachable</td>
              <td>Active / Reachable</td>
              <td><span className="tool-pill tool-pill-ok">Added</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
