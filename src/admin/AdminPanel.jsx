import React, { useState } from "react";
import UsersPanel from "./UsersPanel.jsx";
import RolesPanel from "./RolesPanel.jsx";
import ActiveDirectoryPanel from "./ActiveDirectoryPanel.jsx";
import AuditLogPanel from "./AuditLogPanel.jsx";
import "./admin.css";

const SUBTABS = [
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
      <div className="nt-admin-subtabs">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            className={`nt-admin-subtab ${activeSub === t.id ? "active" : ""}`}
            onClick={() => setActiveSub(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {ActiveComponent && <ActiveComponent />}
    </div>
  );
}