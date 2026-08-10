import React from "react";
import { TOOLS } from "../tools/registry.js";

export default function Toolbar({ active, onNavigate }) {
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
    </div>
  );
}
