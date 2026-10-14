import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import { createTenant, tenantRequest, setMember, removeMember } from "./api.js";
import "./tenants.css";
import TenantGroupAccess from "./TenantGroupAccess.jsx";
import useUnsavedChanges from "../components/useUnsavedChanges.js";
import { canLeaveWorkspace } from "../components/navigation.js";

const ACTION_LABELS = { ipam_subnet_move: "IPAM subnet moved", routing_host_move: "Routing host moved", tenant_create: "Tenant created", membership_set: "Access updated", membership_remove: "Access removed" };

function accessDetails(entry) {
  let details;
  try { details = JSON.parse(entry.details); } catch { return "Details unavailable"; }
  if (entry.action === "tenant_create") return details.name;
  if (entry.action === "ipam_subnet_move") return `${details.cidr}: ${details.sourceTenantName} → ${details.targetTenantName}`;
  if (entry.action === "routing_host_move") return `${details.host}: ${details.sourceTenantName || details.sourceTenantId} → ${details.targetTenantName || details.targetTenantId}`;
  if (entry.action.startsWith('group_')) return `${details.name || 'Group'}${details.username ? ` · ${details.username}` : ''}${details.role ? `: ${details.previousRole || 'no access'} → ${details.role}` : details.previousRole ? `: ${details.previousRole} → no group access` : ''}`;
  const account = details.username || `Account ${details.userId}`;
  return details.role ? `${account}: ${details.previousRole || "no access"} → ${details.role}` : account;
}

export default function TenantsPanel() {
  const { user, tenants = [], tenantId: activeTenantId, refresh } = useAuth();
  const [managedTenantId, setManagedTenantId] = useState(null);
  const tenantId = managedTenantId && tenants.some(item => item.id === managedTenantId) ? managedTenantId : activeTenantId;
  const platformAdmin = user?.role === "admin";
  const tenant = tenants.find((item) => item.id === tenantId);
  const [members, setMembers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [audit, setAudit] = useState([]);
  const [groups, setGroups] = useState([]);
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [role, setRole] = useState("user");
  const [roleEdits, setRoleEdits] = useState({});
  const [confirmRemoval, setConfirmRemoval] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  useUnsavedChanges(members.some(member => roleEdits[member.id] && roleEdits[member.id] !== member.role), busy);
  const load = useCallback(async () => {
    const base = `/${encodeURIComponent(tenantId)}`;
    const [nextMembers, nextRoles, nextAccounts, nextAudit, nextGroups] = await Promise.all([
      tenantRequest(`${base}/members`), tenantRequest(`${base}/roles`),
      tenantRequest(`${base}/users`), tenantRequest(`${base}/audit`), tenantRequest(`${base}/group-access`),
    ]);
    return { nextMembers, nextRoles, nextAccounts, nextAudit, nextGroups };
  }, [tenantId]);

  const apply = ({ nextMembers, nextRoles, nextAccounts, nextAudit, nextGroups }) => {
    setMembers(nextMembers); setRoles(nextRoles); setAccounts(nextAccounts); setAudit(nextAudit); setGroups(nextGroups);
    setRoleEdits(Object.fromEntries(nextMembers.map((member) => [member.id, member.role])));
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setAccountId(""); setConfirmRemoval(null);
    load().then((result) => { if (!cancelled) apply(result); })
      .catch((cause) => { if (!cancelled) setError(cause.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [load]);

  const mutate = async (operation, success) => {
    if (busy) return;
    setBusy(true); setError(null); setNotice("");
    try {
      await operation();
      apply(await load());
      setNotice(success);
      await refresh();
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  };

  return <section className="nt-tenants-panel">
    <h2>Tenants</h2>
    <p className="tool-hint">Accounts are shared. Membership and tool permissions apply separately to each tenant.</p>
    {error && <div className="tool-error" role="alert">{error}
      <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={() => {
        setLoading(true); load().then(apply).then(() => setError(null)).catch((cause) => setError(cause.message)).finally(() => setLoading(false));
      }}>Retry</button>
    </div>}
    <div role="status">{notice}</div>
    {platformAdmin && <form className="nt-tenant-form" onSubmit={(event) => {
      event.preventDefault();
      mutate(async () => { await createTenant(name.trim()); setName(""); }, "Tenant created. Select it below to configure access.");
    }}>
      <label>New tenant<input className="tool-input" value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} /></label>
      <button className="tool-btn" disabled={busy || !name.trim()}>Create tenant</button>
    </form>}
    {platformAdmin && <label className="nt-access-search">Manage access for tenant<select aria-label="Manage access for tenant" className="tool-input" value={tenantId || ''} disabled={busy} onChange={event => { if (canLeaveWorkspace()) setManagedTenantId(event.target.value); }}>{tenants.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
    <h3>Access to {tenant?.name || "selected tenant"}</h3>
    {loading ? <p role="status">Loading tenant access…</p> : <>
      {platformAdmin && <form className="nt-tenant-form" onSubmit={(event) => {
        event.preventDefault();
        mutate(() => setMember(tenantId, Number(accountId), role), "Membership saved.");
      }}>
        <label>Account<select aria-label="Account" className="tool-input" value={accountId} onChange={(event) => setAccountId(event.target.value)} required>
          <option value="">Select an account</option>
          {accounts.map((account) => <option key={account.id} value={account.id}>{account.username} ({account.authSource})</option>)}
        </select></label>
        <label>Tenant role<select aria-label="Tenant role" className="tool-input" value={role} onChange={(event) => setRole(event.target.value)}>
          {roles.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
        </select></label>
        <button className="tool-btn" disabled={busy || !accountId}>Save access</button>
      </form>}
      {!platformAdmin && <p className="tool-hint">A platform administrator grants initial access to additional accounts. You can manage existing members below.</p>}
      <p className="tool-hint">Individual roles override group permissions. Removing an individual assignment restores any inherited group access.</p>
      <div className="tool-table-wrap"><table className="tool-table nt-access-table"><thead><tr><th>Account</th><th>Tenant role</th><th>Actions</th></tr></thead>
        <tbody>{members.map((member) => <tr key={member.id}>
          <td data-label="Account">{member.username} <span className="tool-hint">({member.authSource})</span></td>
          <td data-label="Tenant role">{member.role === "admin" ? "Platform administrator" : <select className="tool-input" aria-label={`Tenant role for ${member.username}`}
            value={roleEdits[member.id] || member.role} disabled={busy} onChange={(event) => setRoleEdits((previous) => ({ ...previous, [member.id]: event.target.value }))}>
            {roles.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
          </select>}</td>
          <td data-label="Actions" className="nt-tenant-actions">
            {member.role !== "admin" && <button className="tool-btn tool-btn-ghost" disabled={busy || roleEdits[member.id] === member.role}
              onClick={() => mutate(() => setMember(tenantId, member.id, roleEdits[member.id]), "Tenant role updated.")}>Save role</button>}
            {member.role === "admin" ? <span className="tool-hint">Global access</span> : confirmRemoval === member.id ? <>
              <span>Remove individual assignment for {member.username}? Group access may remain.</span>
              <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={() => mutate(async () => {
                await removeMember(tenantId, member.id); setConfirmRemoval(null);
              }, "Tenant access removed.")}>Confirm removal</button>
              <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={() => setConfirmRemoval(null)}>Cancel</button>
            </> : <button className="tool-btn tool-btn-ghost" disabled={busy} onClick={() => setConfirmRemoval(member.id)}>Remove access</button>}
          </td>
        </tr>)}</tbody></table></div>
      {members.length === 0 && <p className="tool-empty">No explicit members. Platform administrators can access every tenant.</p>}
      <TenantGroupAccess key={tenantId} tenantId={tenantId} bindings={groups} roles={roles} busy={busy} platformAdmin={platformAdmin} mutate={mutate} />
      <h3>Recent access changes</h3>
      <div className="tool-table-wrap"><table className="tool-table nt-access-table"><thead><tr><th>Time</th><th>Action</th><th>Changed by</th><th>Details</th></tr></thead>
        <tbody>{audit.map((entry) => <tr key={entry.id}><td data-label="Time">{new Date(entry.created_at).toLocaleString()}</td><td data-label="Action">{ACTION_LABELS[entry.action] || entry.action}</td><td data-label="Changed by">{entry.actor_username || "System"}</td><td data-label="Details">{accessDetails(entry)}</td></tr>)}</tbody>
      </table></div>
      {audit.length === 0 && <p className="tool-hint">No access changes recorded.</p>}
    </>}
  </section>;
}
