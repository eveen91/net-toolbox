import React, { useState, useEffect } from "react";
import { TOOLS } from "../tools/registry.js";
import {
  listRoles,
  createRole,
  updateRole,
  deleteRole,
  addRoleAdGroup,
  removeRoleAdGroup,
  getAdSettings,
} from "./api.js";
import "../tools/shared.css";
import "./admin.css";
export default function RolesPanel() {
  const [roles, setRoles] = useState([]);
  const [roleError, setRoleError] = useState(null);
  const [roleEdits, setRoleEdits] = useState({}); // roleId -> permissions[]
  const [savingRoleId, setSavingRoleId] = useState(null);
  const [deletingRoleId, setDeletingRoleId] = useState(null);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRolePermissions, setNewRolePermissions] = useState([]);
  const [creatingRole, setCreatingRole] = useState(false);
  const [adEnabled, setAdEnabled] = useState(false);
  const [newGroupDnByRole, setNewGroupDnByRole] = useState({}); // roleId -> string
  const [groupErrorByRole, setGroupErrorByRole] = useState({}); // roleId -> string
  const [savingGroupRoleId, setSavingGroupRoleId] = useState(null);
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
  getAdSettings()
    .then((settings) => setAdEnabled(!!settings.enabled))
    .catch(() => setAdEnabled(false));
}, []);

const handleAddRoleAdGroup = async (roleId) => {
  const groupDn = (newGroupDnByRole[roleId] || "").trim();
  if (!groupDn) return;
  setGroupErrorByRole((prev) => ({ ...prev, [roleId]: null }));
  setSavingGroupRoleId(roleId);
  try {
    await addRoleAdGroup(roleId, groupDn);
    setNewGroupDnByRole((prev) => ({ ...prev, [roleId]: "" }));
    await loadRoles();
  } catch (e) {
    setGroupErrorByRole((prev) => ({ ...prev, [roleId]: e.message }));
  } finally {
    setSavingGroupRoleId(null);
  }
};

const handleRemoveRoleAdGroup = async (roleId, groupDn) => {
  setGroupErrorByRole((prev) => ({ ...prev, [roleId]: null }));
  setSavingGroupRoleId(roleId);
  try {
    await removeRoleAdGroup(roleId, groupDn);
    await loadRoles();
  } catch (e) {
    setGroupErrorByRole((prev) => ({ ...prev, [roleId]: e.message }));
  } finally {
    setSavingGroupRoleId(null);
  }
};
return (
    <div className="nt-admin-roles">
        <h3>New Role</h3>
        {roleError && <div className="tool-error">{roleError}</div>}

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
                    {adEnabled && (
                      <div className="nt-role-ad-groups">
                        {(role.adGroups || []).map((dn) => (
                          <span key={dn} className="nt-ad-group-chip">
                            {dn}
                            <button
                              type="button"
                              className="nt-ad-group-chip-remove"
                              onClick={() => handleRemoveRoleAdGroup(role.id, dn)}
                              disabled={savingGroupRoleId === role.id}
                              aria-label={`Remove ${dn}`}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                        <div className="nt-ad-group-add">
                          <input
                            className="tool-input nt-ad-group-input"
                            placeholder="AD group DN"
                            value={newGroupDnByRole[role.id] || ""}
                            onChange={(e) =>
                              setNewGroupDnByRole((prev) => ({ ...prev, [role.id]: e.target.value }))
                            }
                          />
                          <button
                            type="button"
                            className="tool-btn tool-btn-ghost"
                            onClick={() => handleAddRoleAdGroup(role.id)}
                            disabled={savingGroupRoleId === role.id || !(newGroupDnByRole[role.id] || "").trim()}
                          >
                            Add
                          </button>
                        </div>
                        {groupErrorByRole[role.id] && (
                          <div className="tool-error nt-ad-group-error">{groupErrorByRole[role.id]}</div>
                        )}
                      </div>
                    )}
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
                    {role.name === "admin" ? (
                      <span className="nt-admin-actions-placeholder">—</span>
                    ) : (
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
      </div>
  );
}