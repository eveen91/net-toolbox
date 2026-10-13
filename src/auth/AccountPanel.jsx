import React from "react";
import ChangePasswordForm from "./ChangePasswordForm.jsx";

export default function AccountPanel({ user, top, onClose, onLogout }) {
  return (
    <div className="nt-account-popover" style={{ top }}>
      <div className="nt-account-popover-header">
        <span className="nt-account-popover-username">{user.username}</span>
        <button
          className="nt-account-popover-close"
          onClick={onClose}
          aria-label="Close account panel"
        >
          ×
        </button>
      </div>
      {user.role && (
        <div className="nt-account-popover-role">Role: {user.role}</div>
      )}
      <div className="nt-account-popover-divider" />
      <div className="nt-account-popover-label">Change password</div>
      <ChangePasswordForm onClose={onClose} />
      {onLogout && <button type="button" className="tool-btn tool-btn-ghost" onClick={onLogout}>Log out</button>}
    </div>
  );
}
