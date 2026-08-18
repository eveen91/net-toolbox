import React, { useState, useEffect } from "react";
import {
  getAdSettings,
  updateAdSettings,
  testAdConnection,
} from "./api.js";
import UsersPanel from "./UsersPanel.jsx";
import "../tools/shared.css";
import "./admin.css";

export default function AdminPanel() {
  const [roles, setRoles] = useState([]);
  const [adConfig, setAdConfig] = useState(null);
  const [adSaving, setAdSaving] = useState(false);
  const [adError, setAdError] = useState(null);
  const [adTestResult, setAdTestResult] = useState(null);
  const [adTesting, setAdTesting] = useState(false);

const loadAdSettings = async () => {
    try {
      const result = await getAdSettings();
      setAdConfig(result);
    } catch (e) {
      setAdError(e.message);
    }
  };

const handleAdFieldChange = (field, value) => {
    setAdConfig((prev) => ({ ...prev, [field]: value }));
  };

const handleSaveAdSettings = async () => {
    setAdError(null);
    setAdSaving(true);
    try {
      const result = await updateAdSettings(adConfig);
      setAdConfig(result);
    } catch (e) {
      setAdError(e.message);
    } finally {
      setAdSaving(false);
    }
  };

const handleTestAdConnection = async () => {
    setAdTestResult(null);
    setAdError(null);
    setAdTesting(true);
    try {
      const result = await testAdConnection({
        host: adConfig.host,
        port: adConfig.port,
        useTls: adConfig.useTls,
      });
      setAdTestResult(result);
    } catch (e) {
      setAdError(e.message);
    } finally {
      setAdTesting(false);
    }
  };

useEffect(() => {
    loadAdSettings();
  }, []);

return (
    <div className="nt-admin-panel">
      <h2>Admin</h2>

<UsersPanel roles={roles} />

<div className="nt-admin-ad-settings">
        <h3>Active Directory</h3>
        {adConfig === null ? (
          <div className="tool-hint">Loading…</div>
        ) : (
          <>
            <label className="tool-hint">
              <input
                type="checkbox"
                checked={adConfig.enabled}
                onChange={(e) => handleAdFieldChange("enabled", e.target.checked)}
              />
              {" "}Enable AD login
            </label>
            <input
              className="tool-input"
              placeholder="Host (e.g. dc01.example.com)"
              value={adConfig.host}
              onChange={(e) => handleAdFieldChange("host", e.target.value)}
            />
            <input
              className="tool-input"
              type="number"
              placeholder="Port"
              value={adConfig.port}
              onChange={(e) => handleAdFieldChange("port", Number(e.target.value))}
            />
            <label className="tool-hint">
              <input
                type="checkbox"
                checked={adConfig.useTls}
                onChange={(e) => handleAdFieldChange("useTls", e.target.checked)}
              />
              {" "}Use TLS
            </label>
            <input
              className="tool-input"
              placeholder="Domain suffix (e.g. example.com)"
              value={adConfig.domainSuffix}
              onChange={(e) => handleAdFieldChange("domainSuffix", e.target.value)}
            />
            <input
              className="tool-input"
              placeholder="Required group DN (optional)"
              value={adConfig.requiredGroupDn || ""}
              onChange={(e) => handleAdFieldChange("requiredGroupDn", e.target.value || null)}
            />
            {!adConfig.requiredGroupDn && (
              <p className="tool-hint nt-admin-ad-warning">
                No required group set — any successfully authenticated
                AD user will be able to log in and get an account here.
              </p>
            )}
            <input
              className="tool-input"
              placeholder="Admin group DN (optional)"
              value={adConfig.adminGroupDn || ""}
              onChange={(e) => handleAdFieldChange("adminGroupDn", e.target.value || null)}
            />
            {adError && <div className="tool-error">{adError}</div>}
            <div className="nt-admin-ad-actions">
              <button
                className="tool-btn tool-btn-primary"
                onClick={handleSaveAdSettings}
                disabled={adSaving}
              >
                {adSaving ? "Saving…" : "Save"}
              </button>
              <button
                className="tool-btn tool-btn-ghost"
                onClick={handleTestAdConnection}
                disabled={adTesting || !adConfig.host}
                type="button"
              >
                {adTesting ? "Testing…" : "Test connection"}
              </button>
            </div>
            {adTestResult && (
              <div className={`nt-admin-ad-test-result ${adTestResult.reachable ? "ok" : "fail"}`}>
                {adTestResult.reachable ? (
                  adTestResult.tlsValid === false ? (
                    <>Reachable, but TLS certificate validation failed: {adTestResult.error}</>
                  ) : (
                    <>Reachable{adTestResult.tlsValid ? " and TLS certificate is valid." : "."}</>
                  )
                ) : (
                  <>Not reachable: {adTestResult.error}</>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}