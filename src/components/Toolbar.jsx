import React, { useState, useRef, useLayoutEffect, useEffect } from "react";
import { createPortal } from "react-dom";
import { visibleTools } from "../tools/registry.js";
import { useAuth } from "../auth/AuthContext.jsx";
import AccountPanel from "../auth/AccountPanel.jsx";
import { canLeaveWorkspace, navigationGroups } from "./navigation.js";

function Chevron() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m3 4.5 3 3 3-3" stroke="currentColor" strokeWidth="1.5" /></svg>;
}

export default function Toolbar({ active, onNavigate }) {
  const { user, logout, loginRequired, tenants = [], tenantId, switchTenant } = useAuth();
  const groups = navigationGroups(visibleTools(user, loginRequired));
  const canAdmin = user?.role === "admin" || user?.tenantRole === "tenant-admin" || !loginRequired;
  const [open, setOpen] = useState(null);
  const [position, setPosition] = useState({ top: 60, left: 12 });
  const toolbarRef = useRef(null);
  const popupRef = useRef(null);
  const triggerRef = useRef(null);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("nt-theme") === "light" ? "light" : "dark"; } catch { return "dark"; }
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("nt-theme", theme); } catch { /* Storage may be unavailable. */ }
  }, [theme]);
  const close = (restore = false) => {
    setOpen(null);
    if (restore) triggerRef.current?.focus();
  };
  const toggle = (id, event) => {
    triggerRef.current = event.currentTarget;
    setOpen((previous) => previous === id ? null : id);
  };
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      const bottom = toolbarRef.current?.getBoundingClientRect().bottom || 60;
      setPosition({ top: bottom + 8, left: Math.max(12, Math.min(rect?.left || 12, window.innerWidth - 332)) });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const pointer = (event) => {
      if (!popupRef.current?.contains(event.target) && !toolbarRef.current?.contains(event.target)) close();
    };
    const key = (event) => {
      if (event.key === "Escape") { event.preventDefault(); close(true); }
    };
    const focus = (event) => {
      if (!popupRef.current?.contains(event.target) && !toolbarRef.current?.contains(event.target)) close();
    };
    const frame = requestAnimationFrame(() => popupRef.current?.querySelector("a, button, input")?.focus());
    document.addEventListener("pointerdown", pointer);
    document.addEventListener("keydown", key);
    document.addEventListener("focusin", focus);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", pointer);
      document.removeEventListener("keydown", key);
      document.removeEventListener("focusin", focus);
    };
  }, [open]);
  useEffect(() => { setOpen(null); }, [active, tenantId, user?.id]);

  const navigate = (event, id) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (id !== active && !canLeaveWorkspace()) return;
    close();
    onNavigate(id);
  };
  const link = (id, name) => <a key={id} href={`#/${id}`} className={active === id ? "active" : ""}
    aria-current={active === id ? "page" : undefined} onClick={(event) => navigate(event, id)}>{name}</a>;
  const disclosure = (id, label, className = "") => <button type="button" className={`nt-navbtn ${className} ${groups.find((group) => group.id === id)?.items.some((tool) => tool.id === active) ? "active" : ""}`}
    aria-expanded={open === id} aria-controls="nt-navigation-popup" onClick={(event) => toggle(id, event)}>{label}<Chevron /></button>;
  const menuGroups = open === "modules" ? groups : groups.filter((group) => group.id === open);

  return <header className="nt-toolbar" ref={toolbarRef}>
    <a className="nt-logo" href="#/home" onClick={(event) => navigate(event, "home")}>net<span>::</span>toolbox</a>
    <nav className="nt-toolbar-navigation" aria-label="Main navigation">
      <a href="#/home" className={`nt-navbtn nt-desktop-nav ${active === "home" ? "active" : ""}`} aria-current={active === "home" ? "page" : undefined} onClick={(event) => navigate(event, "home")}>Workspace</a>
      {groups.map((group) => <React.Fragment key={group.id}>{disclosure(group.id, group.label, "nt-desktop-nav")}</React.Fragment>)}
      {canAdmin && <a href="#/admin" className={`nt-navbtn nt-desktop-nav ${active === "admin" ? "active" : ""}`} aria-current={active === "admin" ? "page" : undefined} onClick={(event) => navigate(event, "admin")}>Administration</a>}
      {disclosure("modules", "Modules", "nt-mobile-nav")}
    </nav>
    <div className="nt-toolbar-right">
      {tenants.length > 0 && <label className="nt-tenant-selector"><span>Tenant</span><select aria-label="Active tenant" title={tenants.find((tenant) => tenant.id === tenantId)?.name} className="tool-input" value={tenantId || ""}
        onChange={(event) => { const id = event.target.value; if (id !== tenantId && canLeaveWorkspace()) { close(); switchTenant(id); } }}>
        {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
      </select></label>}
      <button type="button" className="nt-navbtn nt-theme-toggle" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="1.5"/><path d="M10 4v12a6 6 0 0 0 0-12Z" fill="currentColor"/></svg>
      </button>
      {user && <button type="button" className="nt-navbtn nt-account-trigger" aria-label={`Account: ${user.username}`} aria-expanded={open === "account"} aria-controls="nt-account-popup" onClick={(event) => toggle("account", event)}><span>{user.username}</span><Chevron /></button>}
    </div>
    {open && createPortal(<div ref={popupRef}>
      {open === "account" ? <div id="nt-account-popup"><AccountPanel user={user} top={position.top} onClose={() => close(true)} onLogout={() => { if (canLeaveWorkspace()) { close(); logout(); } }} /></div>
        : <nav id="nt-navigation-popup" className="nt-navigation-popup" aria-label="Choose a module" style={position}>
          {open === "modules" && link("home", "Workspace")}
          {menuGroups.map((group) => <section key={group.id}><h2>{group.label}</h2>{group.items.map((tool) => link(tool.id, tool.name))}</section>)}
          {open === "modules" && canAdmin && link("admin", "Administration")}
        </nav>}
    </div>, document.body)}
  </header>;
}
