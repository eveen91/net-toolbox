import React, { useState } from "react";
import "./routing-map.css";
import RoutingTable from "./RoutingTable.jsx";
import RoutingTest from "./RoutingTest.jsx";
import NetworkVisualization from "./NetworkVisualization.jsx";

// Sub-pages within the Routing Map tool. Add an entry here (and a
// component file next to this one) to add another sub-tab.
const SUBTABS = [
  { id: "table", label: "Routing Map", Component: RoutingTable },
  { id: "test", label: "Routing Test", Component: RoutingTest },
  { id: "visualization", label: "Visualization", Component: NetworkVisualization },
];

export default function RoutingMap() {
  const [activeSub, setActiveSub] = useState(SUBTABS[0].id);
  const ActiveComponent = SUBTABS.find((t) => t.id === activeSub)?.Component;

  return (
    <div>
      <div className="rm-subtabs">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            className={`rm-subtab ${activeSub === t.id ? "active" : ""}`}
            onClick={() => setActiveSub(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {ActiveComponent && <ActiveComponent />}
    </div>
  );
}
