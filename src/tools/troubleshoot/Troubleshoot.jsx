import React, { useState } from "react";
import "./troubleshoot.css";
import DiagnosticsTab from "./DiagnosticsTab.jsx";
import LocateTab from "./LocateTab.jsx";
import ReachabilityTab from "./ReachabilityTab.jsx";
import StpReportTab from "./StpReportTab.jsx";
import InventoryTab from "./InventoryTab.jsx";
import ActivityTab from "./ActivityTab.jsx";

// Sub-pages within the Troubleshoot tool. Add an entry here (and a
// component file next to this one) to add another sub-tab.
const SUBTABS = [
  { id: "diagnostics", label: "Diagnostics", Component: DiagnosticsTab },
  { id: "locate", label: "Locate & Port", Component: LocateTab },
  { id: "reachability", label: "Reachability & Route", Component: ReachabilityTab },
  { id: "stp", label: "STP Report", Component: StpReportTab },
  { id: "inventory", label: "Inventory", Component: InventoryTab },
  { id: "activity", label: "Activity", Component: ActivityTab },
];

export default function Troubleshoot() {
  const [activeSub, setActiveSub] = useState(SUBTABS[0].id);
  const [locateForm, setLocateForm] = useState({ ip: "", username: "", password: "" });
  const ActiveComponent = SUBTABS.find((t) => t.id === activeSub)?.Component;

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Troubleshoot</h2>
        <p>Look up a device on the network and check its health.</p>
      </div>

      <div className="ts-subtabs">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            className={`ts-subtab ${activeSub === t.id ? "active" : ""}`}
            onClick={() => setActiveSub(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {ActiveComponent && (
        <ActiveComponent locateForm={locateForm} setLocateForm={setLocateForm} />
      )}
    </div>
  );
}
