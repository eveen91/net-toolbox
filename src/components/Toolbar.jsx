import React, { useState, useRef, useLayoutEffect, useEffect } from "react";
import { createPortal } from "react-dom";
import { visibleTools } from "../tools/registry.js";
import { useAuth } from "../auth/AuthContext.jsx";
import AccountPanel from "../auth/AccountPanel.jsx";

export default function Toolbar({ active, onNavigate }) {
  const { user, logout, loginRequired } = useAuth();
  const tools = visibleTools(user, loginRequired);
  const [showAccount, setShowAccount] = useState(false);
  const [popoverTop, setPopoverTop] = useState(56);
  const toolbarRef = useRef(null);
  const accountBtnRef = useRef(null);
  const popoverRef = useRef(null);

  // .nt-main is the main content area (sibling of the toolbar). We portal the
  // popover into it so it lives in the page's main content, not the toolbar.
  const mainEl =
    typeof document !== "undefined" ? document.querySelector(".nt-main") : null;

  // Position the popover just under the toolbar, so it never overlaps it.
  useLayoutEffect(() => {
    if (showAccount && toolbarRef.current) {
      setPopoverTop(toolbarRef.current.getBoundingClientRect().bottom);
    }
  }, [showAccount]);

  // Close on outside click / Escape. Since the popover is portaled elsewhere
  // in the DOM, we check both the toggle button and the popover itself.
  useEffect(() => {
    if (!showAccount) return;

    function handlePointerDown(e) {
      const clickedButton = accountBtnRef.current?.contains(e.target);
      const clickedPopover = popoverRef.current?.contains(e.target);
      if (!clickedButton && !clickedPopover) {
        setShowAccount(false);
      }
    }
    function handleKeyDown(e) {
      if (e.key === "Escape") setShowAccount(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showAccount]);

  return (
    <div className="nt-toolbar" ref={toolbarRef}>
      <button className="nt-logo" onClick={() => onNavigate("home")}>
        net<span>::</span>toolbox
      </button>

      <button
        className={`nt-navbtn ${active === "home" ? "active" : ""}`}
        onClick={() => onNavigate("home")}
      >
        Home
      </button>

      {tools.map((tool) => (
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
              ref={accountBtnRef}
              className="nt-toolbar-username nt-toolbar-username-btn"
              onClick={() => setShowAccount((v) => !v)}
            >
              {user.username}
            </button>
            <button className="nt-navbtn" onClick={logout}>
              Log out
            </button>
          </div>
        )}
      </div>

      {showAccount &&
        user &&
        mainEl &&
        createPortal(
          <div ref={popoverRef}>
            <AccountPanel
              user={user}
              top={popoverTop}
              onClose={() => setShowAccount(false)}
            />
          </div>,
          mainEl
        )}
    </div>
  );
}
