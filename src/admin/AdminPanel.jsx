import ViewTabs from "../components/ViewTabs.jsx";
import { canLeaveWorkspace } from "../components/navigation.js";
import TenantsPanel from "../tenants/TenantsPanel.jsx";
import React, { useState } from "react";
import UsersPanel from "./UsersPanel.jsx";
import RolesPanel from "./RolesPanel.jsx";
import ActiveDirectoryPanel from "./ActiveDirectoryPanel.jsx";
import AuditLogPanel from "./AuditLogPanel.jsx";
import "./admin.css";

const SUBTABS = [
  { id: "tenants", label: "Tenants", Component: TenantsPanel },
  { id: "users", label: "Users", Component: UsersPanel },
  { id: "roles", label: "Roles", Component: RolesPanel },
  { id: "ad", label: "Active Directory", Component: ActiveDirectoryPanel },
  { id: "audit", label: "Audit Log", Component: AuditLogPanel },
];

export default function AdminPanel() {
  const [activeSub, setActiveSub] = useState(SUBTABS[0].id);
  const ActiveComponent = SUBTABS.find((t) => t.id === activeSub)?.Component;

return (
    <div className="nt-admin-panel">
      <h2>Admin</h2>
      <ViewTabs items={SUBTABS} value={activeSub} onChange={(id) => { if (canLeaveWorkspace()) setActiveSub(id); }} label="Module views" />
      {ActiveComponent && <ActiveComponent />}
    </div>
  );
}