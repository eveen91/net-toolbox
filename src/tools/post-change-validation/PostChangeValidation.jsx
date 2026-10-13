import ViewTabs from "../../components/ViewTabs.jsx";
import React, { useState } from "react";
import BaselineTab from "./BaselineTab";
import ExecutionTab from "./ExecutionTab";
import DiffViewTab from "./DiffViewTab";
import PirReportTab from "./PirReportTab";
import "./post-change-validation.css";

export default function PostChangeValidation() {
  const [activeTab, setActiveTab] = useState("baseline");
  const [selectedPlan, setSelectedPlan] = useState(null);

  return (
    <div className="tool-container">
      <div className="nt-tool-header">
        <h2>Post-Change Network Validation</h2>
      </div>
      <p className="tool-hint">
        Automated baseline capture, T-01 to T-22 post-change verification, diffing, and PIR evidence generation.
      </p>

      <ViewTabs value={activeTab} onChange={setActiveTab} label="Validation stages" items={[
        {id:'baseline',label:'1. Baseline'}, {id:'execution',label:'2. Execution'}, {id:'diff',label:'3. Diff'}, {id:'pir',label:'4. PIR'}
      ]} />
      {activeTab !== "baseline" && <p className="tool-warning" role="status">Demonstration — execution, diff and sign-off use example data. They do not verify infrastructure or persist an approval.</p>}
      <div className="tool-panel">
        {activeTab === "baseline" && (
          <BaselineTab plan={selectedPlan} onBaselineSaved={() => setActiveTab("execution")} />
        )}
        {activeTab === "execution" && (
          <ExecutionTab plan={selectedPlan} />
        )}
        {activeTab === "diff" && (
          <DiffViewTab />
        )}
        {activeTab === "pir" && (
          <PirReportTab />
        )}
      </div>
    </div>
  );

}
