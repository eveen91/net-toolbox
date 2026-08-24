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
      <div className="tool-section-title">
        <h2>Post-Change Network Validation</h2>
      </div>
      <p className="tool-hint">
        Automated baseline capture, T-01 to T-22 post-change verification, diffing, and PIR evidence generation.
      </p>

      <div className="tabs">
        <div className={`tab ${activeTab === "baseline" ? "active" : ""}`} onClick={() => setActiveTab("baseline")}>1. Pre-Change Baseline</div>
        <div className={`tab ${activeTab === "execution" ? "active" : ""}`} onClick={() => setActiveTab("execution")}>2. Execution</div>
        <div className={`tab ${activeTab === "diff" ? "active" : ""}`} onClick={() => setActiveTab("diff")}>3. Visual Diff</div>
        <div className={`tab ${activeTab === "pir" ? "active" : ""}`} onClick={() => setActiveTab("pir")}>4. PIR & Sign-off</div>
      </div>

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
