import React, { useEffect, useMemo, useRef, useState } from "react";
import "./routing-map.css";
import {
  parseRoutingData,
  serializeHosts,
  parseDeviceRouteOutput,
  upsertHost,
  EXAMPLE,
  EXAMPLE_DEVICE_OUTPUT,
} from "./logic.js";
import {
  listRoutingHosts,
  exportRoutingHosts,
  getRoutingHost,
  saveRoutingHost,
  deleteRoutingHost,
} from "./api.js";

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/** Prefer saved interface rows; otherwise build the list from connected routes. */
function interfacesForDisplay(detail) {
  const stored = detail?.interfaces || [];
  if (stored.length > 0) return stored;
  const seen = new Set();
  const out = [];
  for (const r of detail?.routes || []) {
    if ((r.nextHop || "").toLowerCase() !== "directly connected") continue;
    const name = (r.interface || "").trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push({ name, ipAddress: r.network, description: null });
  }
  return out;
}

/**
 * Inline double-click-to-edit text field, used for both an interface's
 * address and its description. `required` blocks committing an empty
 * value (the backend's ipAddress field is mandatory) — the field just
 * reverts to its previous value instead of saving a blank.
 */
function EditableField({ value, disabled, required, onCommit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;

  useEffect(() => {
    if (!editing) setDraft(value || "");
  }, [value, editing]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commit = async () => {
    const next = draftRef.current.trim();
    const prev = (value || "").trim();
    setEditing(false);
    if (next === prev) return;
    if (!next && required) {
      setDraft(value || "");
      return;
    }
    setSaving(true);
    try {
      await onCommit(next || null);
    } catch {
      setDraft(value || "");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="rm-inline-input"
        value={draft}
        disabled={saving}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          void commit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          } else if (e.key === "Escape") {
            e.preventDefault();
            setDraft(value || "");
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <span
      className={`rm-editable-desc${disabled ? " is-disabled" : ""}`}
      title={disabled ? undefined : "Double-click to edit"}
      onDoubleClick={() => {
        if (!disabled && !saving) setEditing(true);
      }}
    >
      {saving ? "Saving…" : value || "—"}
    </span>
  );
}

function HostDetail({ detail, deleting, onDelete, onDetailUpdated }) {
  const ifaces = interfacesForDisplay(detail);
  const [ifaceError, setIfaceError] = useState(null);

  // Saves one interface's address and/or description, keeping the rest of
  // that interface (and every other interface) untouched.
  const saveInterfaceField = async (ifaceName, patch) => {
    setIfaceError(null);
    const interfaces = ifaces.map((i) =>
      i.name === ifaceName
        ? { name: i.name, ipAddress: i.ipAddress, description: i.description || null, ...patch }
        : { name: i.name, ipAddress: i.ipAddress, description: i.description || null }
    );
    const routes = (detail.routes || []).map((r) => ({
      network: r.network,
      nextHop: r.nextHop,
      interface: r.interface || null,
    }));
    const saved = await saveRoutingHost(detail.host, routes, interfaces);
    onDetailUpdated(saved);
  };

  return (
    <>
      <div className="tool-section-title">
        {detail.host}
        <span className="tool-hint">
          {ifaces.length} iface{ifaces.length !== 1 ? "s" : ""} · {detail.routes.length} route
          {detail.routes.length !== 1 ? "s" : ""} · saved {formatTimestamp(detail.updatedAt)}
        </span>
        <button className="tool-btn tool-btn-ghost rm-delete-btn" onClick={onDelete} disabled={deleting}>
          {deleting ? "Deleting…" : "Delete host"}
        </button>
      </div>

      <div style={{ marginBottom: 20 }}>
        <h3 className="rm-section-sub-title">Interfaces</h3>
        {ifaceError && <div className="tool-error">{ifaceError}</div>}
        <div className="tool-table-wrap rm-table-wrap-full">
          <table className="tool-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Address</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {ifaces.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ color: "var(--muted)" }}>
                    No interfaces for this host.
                  </td>
                </tr>
              )}
              {ifaces.map((i) => (
                <tr key={i.name}>
                  <td>{i.name}</td>
                  <td>
                    <EditableField
                      value={i.ipAddress}
                      disabled={deleting}
                      required
                      onCommit={async (ipAddress) => {
                        try {
                          await saveInterfaceField(i.name, { ipAddress });
                        } catch (e) {
                          setIfaceError(e.message);
                          throw e;
                        }
                      }}
                    />
                  </td>
                  <td>
                    <EditableField
                      value={i.description}
                      disabled={deleting}
                      onCommit={async (description) => {
                        try {
                          await saveInterfaceField(i.name, { description });
                        } catch (e) {
                          setIfaceError(e.message);
                          throw e;
                        }
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="rm-section-sub-title">Routes</h3>
        <div className="tool-table-wrap rm-table-wrap-full">
          <table className="tool-table">
            <thead>
              <tr>
                <th>Network</th>
                <th>Next hop</th>
                <th>Interface</th>
              </tr>
            </thead>
            <tbody>
              {detail.routes.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ color: "var(--muted)" }}>
                    No routes for this host.
                  </td>
                </tr>
              )}
              {detail.routes.map((r, i) => (
                <tr key={i}>
                  <td>{r.network}</td>
                  <td>{r.nextHop}</td>
                  <td>{r.interface || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default function RoutingMap() {
  const [raw, setRaw] = useState(EXAMPLE);
  const { hosts: draftHosts, warnings } = useMemo(() => parseRoutingData(raw), [raw]);

  const [savedHosts, setSavedHosts] = useState([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState(null);

  const [selectedHost, setSelectedHost] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);
  const [importing, setImporting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [deviceOutput, setDeviceOutput] = useState("");
  const [deviceImportMessage, setDeviceImportMessage] = useState(null);

  const refreshList = async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listRoutingHosts();
      setSavedHosts(data);
    } catch (e) {
      setListError(e.message);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
  }, []);

  const selectHost = async (host) => {
    setSelectedHost(host);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const data = await getRoutingHost(host);
      setSelectedDetail(data);
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleSave = async () => {
    setSaveMessage(null);
    if (draftHosts.length === 0) {
      setSaveMessage({ ok: false, text: "Nothing to save — paste at least one @host block first." });
      return;
    }
    setSaving(true);
    const outcomes = await Promise.allSettled(
      draftHosts.map((h) =>
        saveRoutingHost(
          h.host,
          (h.routes || []).map((r) => ({
            network: r.network,
            nextHop: r.nextHop,
            interface: r.interface || null,
          })),
          (h.interfaces || []).map((i) => ({
            name: i.name,
            ipAddress: i.ipAddress,
            description: i.description || null,
          }))
        )
      )
    );
    const failures = outcomes
      .map((o, i) => (o.status === "rejected" ? { host: draftHosts[i].host, error: o.reason.message } : null))
      .filter(Boolean);
    const successCount = outcomes.length - failures.length;

    if (failures.length === 0) {
      setSaveMessage({ ok: true, text: `Saved ${successCount} host${successCount !== 1 ? "s" : ""} to the database.` });
    } else {
      setSaveMessage({
        ok: false,
        text: `Saved ${successCount} of ${outcomes.length}. Failed: ${failures
          .map((f) => `${f.host} (${f.error})`)
          .join("; ")}`,
      });
    }

    await refreshList();
    setSaving(false);
  };

  const handleLoadFromDb = async () => {
    setImporting(true);
    setListError(null);
    try {
      const data = await exportRoutingHosts();
      setRaw(data.length > 0 ? serializeHosts(data) : "");
      setSavedHosts(
        data.map((h) => ({
          host: h.host,
          routeCount: (h.routes || []).length,
          interfaceCount: (h.interfaces || []).length,
          updatedAt: h.updatedAt,
        }))
      );
    } catch (e) {
      setListError(e.message);
    } finally {
      setImporting(false);
    }
  };

  const handleImportDevice = () => {
    setDeviceImportMessage(null);
    if (!deviceOutput.trim()) return;

    const { host, routes, interfaces, warnings } = parseDeviceRouteOutput(deviceOutput);
    if (routes.length === 0 && interfaces.length === 0) {
      setDeviceImportMessage({ ok: false, text: "No routes found in the pasted output." });
      return;
    }

    setRaw((prev) => upsertHost(prev, host, routes, interfaces));
    setSaveMessage(null);
    const ifaceNote =
      interfaces.length > 0
        ? ` and ${interfaces.length} interface${interfaces.length !== 1 ? "s" : ""} (from connected routes)`
        : "";
    setDeviceImportMessage({
      ok: warnings.length === 0,
      text:
        `Imported ${routes.length} route${routes.length !== 1 ? "s" : ""}${ifaceNote} into the draft for "${host}".` +
        (warnings.length > 0 ? `\n${warnings.join("\n")}` : "") +
        `\nReview the draft, then click "Save to database".`,
    });
    setDeviceOutput("");
  };

  const handleDelete = async () => {
    if (!selectedHost) return;
    if (!window.confirm(`Delete the saved routing table for "${selectedHost}"? This can't be undone.`)) return;
    setDeleting(true);
    try {
      await deleteRoutingHost(selectedHost);
      setSelectedHost(null);
      setSelectedDetail(null);
      await refreshList();
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <div className="nt-tool-header">
        <h2>Routing map</h2>
        <p>Paste routes by hand or import "show route" output, save to the database, then pick a host to view it.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>
                Routing tables (draft){" "}
                <span className="tool-hint">
                  @hostname, %interface cidr [- desc], then "network -&gt; next hop[, interface]" — use
                  "directly-connected" for local routes
                </span>
              </span>
            </div>
            <textarea
              className="tool-textarea"
              style={{ minHeight: 220 }}
              value={raw}
              onChange={(e) => {
                setRaw(e.target.value);
                setSaveMessage(null);
              }}
            />
          </div>

          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save to database"}
            </button>
            <button className="tool-btn tool-btn-ghost" onClick={() => setRaw(EXAMPLE)}>
              Load example
            </button>
          </div>
          <div className="tool-actions" style={{ marginTop: 8 }}>
            <button className="tool-btn tool-btn-ghost" onClick={handleLoadFromDb} disabled={importing}>
              {importing ? "Loading…" : "Load from database"}
            </button>
          </div>

          {saveMessage && (
            <div className={saveMessage.ok ? "rm-notice rm-notice-ok" : "tool-error"}>{saveMessage.text}</div>
          )}
          {warnings.length > 0 && (
            <div className="tool-error">
              {warnings.length} line{warnings.length > 1 ? "s" : ""} skipped in the draft:
              {"\n"}
              {warnings.join("\n")}
            </div>
          )}

          <div className="rm-divider" />
          <div className="rm-section-label">Import from device output</div>
          <div className="tool-field">
            <div className="tool-label">
              <span className="tool-hint">
                paste "show route" / "show ip route" CLI output — connected (C) lines become interfaces
              </span>
            </div>
            <textarea
              className="tool-textarea"
              style={{ minHeight: 140 }}
              value={deviceOutput}
              onChange={(e) => {
                setDeviceOutput(e.target.value);
                setDeviceImportMessage(null);
              }}
              placeholder={EXAMPLE_DEVICE_OUTPUT}
            />
          </div>
          <div className="tool-actions">
            <button className="tool-btn tool-btn-primary" onClick={handleImportDevice}>
              Import into draft
            </button>
            <button className="tool-btn tool-btn-ghost" onClick={() => setDeviceOutput(EXAMPLE_DEVICE_OUTPUT)}>
              Load example
            </button>
          </div>
          {deviceImportMessage && (
            <div className={deviceImportMessage.ok ? "rm-notice rm-notice-ok" : "tool-error"}>
              {deviceImportMessage.text}
            </div>
          )}

          <div className="rm-divider" />
          <div className="rm-section-label">
            Saved hosts <span className="tool-hint">{savedHosts.length}</span>
            <button className="tool-btn tool-btn-ghost rm-refresh" onClick={refreshList} disabled={listLoading}>
              {listLoading ? "…" : "Refresh"}
            </button>
          </div>
          {listError && <div className="tool-error">{listError}</div>}
          <div className="rm-host-list">
            {!listLoading && savedHosts.length === 0 && !listError && (
              <div className="tool-hint">Nothing saved yet — edit the draft above and click Save.</div>
            )}
            {savedHosts.map((h) => (
              <button
                key={h.host}
                className={`rm-host-item ${selectedHost === h.host ? "active" : ""}`}
                onClick={() => selectHost(h.host)}
              >
                <span className="rm-host-name">{h.host}</span>
                <span className="rm-host-count">
                  {h.interfaceCount != null ? `${h.interfaceCount} ifaces · ` : ""}
                  {h.routeCount}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="tool-panel">
          {!selectedHost && (
            <div className="tool-empty">Select a saved host from the list to view its interfaces and routes.</div>
          )}

          {selectedHost && detailLoading && <div className="tool-empty">Loading {selectedHost}…</div>}

          {selectedHost && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}

          {selectedHost && !detailLoading && selectedDetail && (
            <HostDetail
              detail={selectedDetail}
              deleting={deleting}
              onDelete={handleDelete}
              onDetailUpdated={setSelectedDetail}
            />
          )}
        </div>
      </div>
    </div>
  );
}
