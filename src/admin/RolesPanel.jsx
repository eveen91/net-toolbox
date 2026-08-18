import React, { useState, useEffect } from "react";
import { TOOLS } from "../tools/registry.js";
import { listRoles, createRole, updateRole, deleteRole } from "./api.js";
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
}, []);
return (
    <div>
      {/* JSX_GOES_HERE */}
    </div>
  );
}