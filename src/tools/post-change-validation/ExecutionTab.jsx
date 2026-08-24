import React, { useState } from "react";

const SAMPLE_TESTS = [
  { id: "T-01", layer: "Control Plane", desc: "Check Point Cluster Health", status: "PASS", detail: "Active/Standby verified" },
  { id: "T-02", layer: "Control Plane", desc: "Check Point Sync State", status: "PASS", detail: "0 sync errors" },
  { id: "T-04", layer: "Control Plane", desc: "Aruba VSX Sync", status: "PASS", detail: "In-sync, no split-brain" },
  { id: "T-08", layer: "Layer 2", desc: "VLAN Tagging & Presence", status: "PASS", detail: "VLAN 200 operational" },
  { id: "T-11", layer: "Layer 3", desc: "Routing Table Entry", status: "PASS", detail: "Route 10.200.0.0/24 present" },
  { id: "T-16b", layer: "Security Policy", desc: "Negative Isolation (VLAN 200 -> Mgmt)", status: "PASS", detail: "Dropped & logged cleanly" },
  { id: "T-18", layer: "Data Plane", desc: "Path MTU Integrity", status: "PASS", detail: "1500 MTU verified, 0 fragmentation" },
];

export default function ExecutionTab({ plan }) {
  const [running, setRunning] = useState(false);
  const [testResults, setTestResults] = useState([]);
  const [progress, setProgress] = useState(0);

  const handleStartRun = () => {
    setRunning(true);
    setTestResults([]);
    setProgress(10);

    let current = 0;
    const interval = setInterval(() => {
      if (current < SAMPLE_TESTS.length) {
        setTestResults((prev) => [...prev, SAMPLE_TESTS[current]]);
        current += 1;
        setProgress(Math.round((current / SAMPLE_TESTS.length) * 100));
      } else {
        clearInterval(interval);
        setRunning(false);
      }
    }, 600);
  };

  return (
    <div>
      <div className="tool-section-title">Test Execution & Live Grid</div>
      <p className="tool-hint" style={{ marginBottom: "20px" }}>
        Execute T-01 through T-22 modular tests against configured devices.
      </p>

      <div className="tool-actions" style={{ marginBottom: "20px" }}>
        <button
          className="tool-btn tool-btn-primary"
          onClick={handleStartRun}
          disabled={running}
        >
          {running ? "Running Tests..." : "Launch Validation Suite"}
        </button>
      </div>

      {running && (
        <div style={{ width: "100%", height: "6px", background: "var(--border-soft)", borderRadius: "4px", overflow: "hidden", marginBottom: "20px" }}>
          <div style={{ width: `${progress}%`, height: "100%", background: "var(--accent)", transition: "width 0.3s ease" }}></div>
        </div>
      )}

      {testResults.length > 0 && (
        <div className="tool-table-wrap">
          <table className="tool-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Layer</th>
                <th>Description</th>
                <th>Status</th>
                <th>Result Details</th>
              </tr>
            </thead>
            <tbody>
              {testResults.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.id}</strong></td>
                  <td>{t.layer}</td>
                  <td>{t.desc}</td>
                  <td>
                    <span className={`tool-pill ${t.status === "PASS" ? "tool-pill-ok" : "tool-pill-no"}`}>
                      {t.status}
                    </span>
                  </td>
                  <td>{t.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
