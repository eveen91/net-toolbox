import ViewTabs from "../../components/ViewTabs.jsx";
import { canLeaveWorkspace } from "../../components/navigation.js";
import React, { useState } from "react";
import "./routing-map.css";
import RoutingTable from "./RoutingTable.jsx";
import RoutingTest from "./RoutingTest.jsx";
import NetworkVisualization from "./NetworkVisualization.jsx";

// Sub-pages within the Routing Map tool. Add an entry here (and a
// component file next to this one) to add another sub-tab.
const SUBTABS = [
  { id: "table", label: "Hosts", Component: RoutingTable },
  { id: "test", label: "Routing Test", Component: RoutingTest },
  { id: "visualization", label: "Topology", Component: NetworkVisualization },
];

export default function RoutingMap() {
  const [activeSub, setActiveSub] = useState(SUBTABS[0].id);
  const ActiveComponent = SUBTABS.find((t) => t.id === activeSub)?.Component;

  return (
    <div>
      <ViewTabs items={SUBTABS} value={activeSub} onChange={(id) => { if (canLeaveWorkspace()) setActiveSub(id); }} label="Module views" />

      {ActiveComponent && <ActiveComponent />}
    </div>
  );
}
