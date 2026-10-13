import React from "react";
import { visibleTools } from "../tools/registry.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { navigationGroups } from "../components/navigation.js";

export default function HomePage({ onOpen }) {
  const { user, loginRequired } = useAuth();
  const tools = visibleTools(user, loginRequired);

  return (
    <div>
      <div className="nt-hero">
        <h1>
          net<span>::</span>toolbox
        </h1>
        <p>
          A self-hosted workspace for network infrastructure, diagnostics and planning.
          Calculators run in your browser; operational tools use your toolbox server.
        </p>
      </div>

      {navigationGroups(tools).map((group) => <section className="nt-workspace-section" key={group.id}>
        <h2>{group.label}</h2>
        <div className="nt-grid">
        {group.items.map((tool) => (
          <button type="button"
            key={tool.id}
            className={`nt-card ${tool.status === "soon" ? "soon" : ""}`}
            onClick={() => tool.status === "live" && onOpen(tool.id)}
          >
            <div className="nt-card-top">
              <div className="nt-card-icon">{tool.icon}</div>
              <span className={`nt-pill ${tool.status === "live" ? "nt-pill-live" : "nt-pill-soon"}`}>
                {tool.status === "live" ? "live" : "coming soon"}
              </span>
            </div>
            <div className="nt-card-name">{tool.name}</div>
            <div className="nt-card-desc">{tool.tagline}</div>
          </button>
        ))}
        </div>
      </section>)}
    </div>
  );
}
