import React, { useState, useEffect } from "react";
import { TOOLS } from "../tools/registry.js";
import {
  listRoles,
  createRole,
  updateRole,
  deleteRole,
  getAdSettings,
  updateAdSettings,
  testAdConnection,
} from "./api.js";
import UsersPanel from "./UsersPanel.jsx";
import "./admin.css";

export default function AdminPanel() {
  const [roles, setRoles] = useState([]);
  const [adConfig, setAdConfig] = useState(null);
  const [adSaving, setAdSaving] = useState(false);
  const [adError, setAdError] = useState(null);
  const [adTestResult, setAdTestResult] = useState(null);
  const [adTesting, setAdTesting] = useState(false);

const [roleError, setRoleError] = useState(null);
  const [roleEdits, setRoleEdits] = useState({}); // roleId -> permissions[]
  const [savingRoleId, setSavingRoleId] = useState(null);
  const [deletingRoleId, setDeletingRoleId] = useState(null);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRolePermissions, setNewRolePermissions] = useState([]);
  const [creatingRole, setCreatingRole] = useState(false);

const loadAdSettings = async () => {
    try {
      const result = await getAdSettings();
      setAdConfig(result);
    } catch (e) {
      setAdError(e.message);
    }
  };

const loadRoles = async () => {
    setRoleError(null);
    try {
      const result = await listRoles();
      setRoles(result);
      const edits = {};
      for (const role of result) {
        edits[role.id] = role.permissions;
      }
      setRoleEdits(edits);
    } catch (e) {
      setRoleError(e.message);
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

const toggleRoleEditPermission = (roleId, toolId) => {
    setRoleEdits((prev) => {
      const current = prev[roleId] || [];
      const next = current.includes(toolId)
        ? current.filter((id) => id !== toolId)
        : [...current, toolId];
      return { ...prev, [roleId]: next };
    });
  };

const handleSaveRole = async (roleId) => {
    setRoleError(null);
    setSavingRoleId(roleId);
    try {
      await updateRole(roleId, roleEdits[roleId] || []);
      await loadRoles();
    } catch (e) {
      setRoleError(e.message);
    } finally {
      setSavingRoleId(null);
    }
  };

const handleDeleteRole = async (roleId) => {
    setRoleError(null);
    setDeletingRoleId(roleId);
    try {
      await deleteRole(roleId);
      await loadRoles();
    } catch (e) {
      setRoleError(e.message);
    } finally {
      setDeletingRoleId(null);
    }
  };

const toggleNewRolePermission = (toolId) => {
    setNewRolePermissions((prev) =>
      prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId]
    );
  };

const handleCreateRole = async (e) => {
    e.preventDefault();
    setRoleError(null);
    setCreatingRole(true);
    try {
      await createRole(newRoleName.trim(), newRolePermissions);
      setNewRoleName("");
      setNewRolePermissions([]);
      await loadRoles();
    } catch (e2) {
      setRoleError(e2.message);
    } finally {
      setCreatingRole(false);
    }
  };

const isRoleDirty = (role) => {
    const edited = roleEdits[role.id] || [];
    if (edited.length !== role.permissions.length) return true;
    const a = [...edited].sort();
    const b = [...role.permissions].sort();
    return a.some((v, i) => v !== b[i]);
  };

useEffect(() => {
    loadRoles();
    loadAdSettings();
  }, []);

return (
    <div className="nt-admin-panel">
      <h2>Admin</h2>

<UsersPanel roles={roles} />

<div className="nt-admin-roles">
        <h3>Roles</h3>
        <p className="tool-hint">
          Choose which tools each role can access. "admin" always has access to everything,
          plus this Config Panel, and can't be edited.
        </p>
        {roleError && <div className="tool-error">{roleError}</div>}

<div className="tool-table-wrap">
          <table className="tool-table nt-roles-table">
            <thead>
              <tr>
                <th>Role</th>
                {TOOLS.map((tool) => (
                  <th key={tool.id}>{tool.name}</th>
                ))}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roles.map((role) => (
                <tr key={role.id}>
                  <td>
                    {role.name}
                    {role.isBuiltin && <span className="nt-role-badge">built-in</span>}
                  </td>
                  {role.name === "admin" ? (
                    <td colSpan={TOOLS.length} className="tool-hint">
                      All features
                    </td>
                  ) : (
                    TOOLS.map((tool) => (
                      <td key={tool.id} className="nt-role-checkbox-cell">
                        <input
                          type="checkbox"
                          checked={(roleEdits[role.id] || []).includes(tool.id)}
                          onChange={() => toggleRoleEditPermission(role.id, tool.id)}
                        />
                      </td>
                    ))
                  )}
                  <td className="nt-admin-actions">
                    {role.name !== "admin" && (
                      <>
                        <button
                          className="tool-btn tool-btn-ghost"
                          onClick={() => handleSaveRole(role.id)}
                          disabled={savingRoleId === role.id || !isRoleDirty(role)}
                        >
                          {savingRoleId === role.id ? "Saving…" : "Save"}
                        </button>
                        <button
                          className="tool-btn tool-btn-ghost"
                          onClick={() => handleDeleteRole(role.id)}
                          disabled={deletingRoleId === role.id}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

<form className="nt-admin-create-form" onSubmit={handleCreateRole}>
          <input
            className="tool-input"
            placeholder="New role name"
            value={newRoleName}
            onChange={(e) => setNewRoleName(e.target.value)}
          />
          <div className="nt-new-role-checkboxes">
            {TOOLS.map((tool) => (
              <label key={tool.id} className="nt-role-checkbox-label">
                <input
                  type="checkbox"
                  checked={newRolePermissions.includes(tool.id)}
                  onChange={() => toggleNewRolePermission(tool.id)}
                />
                {tool.name}
              </label>
            ))}
          </div>
          <button
            className="tool-btn tool-btn-primary"
            type="submit"
            disabled={creatingRole || !newRoleName.trim()}
          >
            {creatingRole ? "Creating…" : "Create role"}
          </button>
        </form>
      </div>

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