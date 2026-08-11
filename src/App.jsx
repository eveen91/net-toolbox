import React, { useState } from "react";
import Toolbar from "./components/Toolbar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import HomePage from "./pages/HomePage.jsx";
import { TOOLS } from "./tools/registry.js";
import "./tools/shared.css";

export default function App() {
  const [active, setActive] = useState("home");
  const activeTool = TOOLS.find((t) => t.id === active);

  return (
    <div>
      <Toolbar active={active} onNavigate={setActive} />

      <div className="nt-main">
        {active === "home" && <HomePage onOpen={setActive} />}

        {active !== "home" && activeTool && activeTool.Component && (
          <>
            <button className="nt-back" onClick={() => setActive("home")}>
              ← All tools
            </button>
            <ErrorBoundary resetKey={active}>
              <activeTool.Component />
            </ErrorBoundary>
          </>
        )}
      </div>
    </div>
  );
}
