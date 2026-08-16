import React from "react";
import { visibleTools } from "../tools/registry.js";
import { useAuth } from "../auth/AuthContext.jsx";

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
          A small set of browser-based networking tools. Pick one below — everything runs
          locally, nothing leaves your browser.
        </p>
      </div>

      <div className="nt-grid">
        {tools.map((tool) => (
          <div
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
          </div>
        ))}
      </div>
    </div>
  );
}
