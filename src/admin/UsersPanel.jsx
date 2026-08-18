import React, { useState, useEffect } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import {
  listUsers,
  createUser,
  deleteUser,
  resetPassword,
  updateUserRole,
  setRequireLogin,
} from "./api.js";
import "./admin.css";
export default function UsersPanel({ roles }) {
  const { user, loginRequired, refresh } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState(null);
  const [resettingId, setResettingId] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState("user");
  const [creating, setCreating] = useState(false);
  const [editingRoleUserId, setEditingRoleUserId] = useState(null);
  const [editingRoleValue, setEditingRoleValue] = useState("user");
const loadUsers = async () => {
    setError(null);
    try {
      const result = await listUsers();
      setUsers(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

useEffect(() => {
    loadUsers();
  }, []);

const handleDelete = async (userId) => {
    setError(null);
    try {
      await deleteUser(userId);
      setConfirmingDeleteId(null);
      await loadUsers();
    } catch (e) {
      setError(e.message);
    }
  };

const handleResetPassword = async (userId) => {
    setError(null);
    try {
      await resetPassword(userId, newPassword);
      setResettingId(null);
      setNewPassword("");
    } catch (e) {
      setError(e.message);
    }
  };

const handleSaveRoleAssignment = async (userId) => {
    setError(null);
    try {
      await updateUserRole(userId, editingRoleValue);
      setEditingRoleUserId(null);
      await loadUsers();
      if (user?.id === userId) {
        await refresh();
      }
    } catch (e) {
      setError(e.message);
    }
  };

const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await createUser(newUsername.trim(), newUserPassword, newUserRole);
      setNewUsername("");
      setNewUserPassword("");
      setNewUserRole("user");
      await loadUsers();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setCreating(false);
    }
  };

const handleToggleRequireLogin = async () => {
    setError(null);
    try {
      await setRequireLogin(!loginRequired);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  };

const hasAdminUser = users.some((u) => u.role === "admin");

if (loading) return <div className="tool-empty">Loading users…</div>;

return (
    <div className="nt-admin-panel">
      <h2>Users</h2>
      {error && <div className="tool-error">{error}</div>}
      <div className="tool-table-wrap">
        <table className="tool-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>
                  {editingRoleUserId === u.id ? (
                    <select
                      className="tool-input"
                      value={editingRoleValue}
                      onChange={(e) => setEditingRoleValue(e.target.value)}
                    >
                      <option value="admin">admin</option>
                      {roles
                        .filter((r) => r.name !== "admin")
                        .map((r) => (
                          <option key={r.id} value={r.name}>
                            {r.name}
                          </option>
                        ))}
                    </select>
                  ) : (
                    u.role
                  )}
                </td>
                <td className="nt-admin-actions">
                  {resettingId === u.id ? (
                    <>
                      <input
                        className="tool-input"
                        type="password"
                        placeholder="New password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                      />
                      <button className="tool-btn tool-btn-ghost" onClick={() => handleResetPassword(u.id)}>
                        Save
                      </button>
                      <button
                        className="tool-btn tool-btn-ghost"
                        onClick={() => {
                          setResettingId(null);
                          setNewPassword("");
                        }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : confirmingDeleteId === u.id ? (
                    <>
                      <span className="tool-hint">Delete {u.username}?</span>
                      <button className="tool-btn tool-btn-ghost" onClick={() => handleDelete(u.id)}>
                        Confirm
                      </button>
                      <button className="tool-btn tool-btn-ghost" onClick={() => setConfirmingDeleteId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : editingRoleUserId === u.id ? (
                    <>
                      <button className="tool-btn tool-btn-ghost" onClick={() => handleSaveRoleAssignment(u.id)}>
                        Save
                      </button>
                      <button className="tool-btn tool-btn-ghost" onClick={() => setEditingRoleUserId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="tool-btn tool-btn-ghost"
                        onClick={() => {
                          setEditingRoleUserId(u.id);
                          setEditingRoleValue(u.role);
                        }}
                      >
                        Change role
                      </button>
                      <button className="tool-btn tool-btn-ghost" onClick={() => setResettingId(u.id)}>
                        Reset password
                      </button>
                      <button className="tool-btn tool-btn-ghost" onClick={() => setConfirmingDeleteId(u.id)}>
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
<form className="nt-admin-create-form" onSubmit={handleCreate}>
        <input
          className="tool-input"
          placeholder="Username"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
        />
        <input
          className="tool-input"
          type="password"
          placeholder="Password"
          value={newUserPassword}
          onChange={(e) => setNewUserPassword(e.target.value)}
        />
        <select
          className="tool-input"
          value={newUserRole}
          onChange={(e) => setNewUserRole(e.target.value)}
        >
          <option value="admin">admin</option>
          {roles
            .filter((r) => r.name !== "admin")
            .map((r) => (
              <option key={r.id} value={r.name}>
                {r.name}
              </option>
            ))}
        </select>
        <button
          className="tool-btn tool-btn-primary"
          type="submit"
          disabled={creating || !newUsername.trim() || !newUserPassword}
        >
          {creating ? "Creating…" : "Create user"}
        </button>
      </form>
<div className="nt-admin-settings">
        <div className="tool-hint">
          Login is currently <strong>{loginRequired ? "required" : "not required"}</strong>.
        </div>
        <button
          className="tool-btn tool-btn-ghost"
          onClick={handleToggleRequireLogin}
          disabled={!hasAdminUser}
        >
          {loginRequired ? "Disable login requirement" : "Enable login requirement"}
        </button>
        {!hasAdminUser && (
          <p className="tool-hint">
            Create an admin user above before changing this setting.
          </p>
        )}
      </div>
    </div>
  );
}