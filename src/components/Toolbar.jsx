import React, { useState } from "react";
import { TOOLS } from "../tools/registry.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ChangePasswordForm from "../auth/ChangePasswordForm.jsx";

export default function Toolbar({ active, onNavigate }) {
  const { user, logout, loginRequired } = useAuth();
  const [showChangePassword, setShowChangePassword] = useState(false);

  return (
    <div className="nt-toolbar">
      <button className="nt-logo" onClick={() => onNavigate("home")}>
        net<span>::</span>toolbox
      </button>

      <button
        className={`nt-navbtn ${active === "home" ? "active" : ""}`}
        onClick={() => onNavigate("home")}
      >
        Home
      </button>

      {TOOLS.map((tool) => (
        <button
          key={tool.id}
          className={`nt-navbtn ${active === tool.id ? "active" : ""} ${
            tool.status !== "live" ? "disabled" : ""
          }`}
          onClick={() => tool.status === "live" && onNavigate(tool.id)}
          title={tool.status !== "live" ? "Coming soon" : undefined}
        >
          {tool.name}
        </button>
      ))}

      <div className="nt-toolbar-right">
        {(user?.role === "admin" || !loginRequired) && (
          <button
            className={`nt-navbtn ${active === "admin" ? "active" : ""}`}
            onClick={() => onNavigate("admin")}
          >
            Config Panel
          </button>
        )}

        {user && (
          <div className="nt-toolbar-user">
            <button
              className="nt-toolbar-username nt-toolbar-username-btn"
              onClick={() => setShowChangePassword((v) => !v)}
            >
              {user.username}
            </button>
            {showChangePassword && (
              <ChangePasswordForm onClose={() => setShowChangePassword(false)} />
            )}
            <button className="nt-navbtn" onClick={logout}>
              Log out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}