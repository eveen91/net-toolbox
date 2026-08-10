import React, { useEffect, useMemo, useState } from "react";
import "./routing-map.css";
import { parseRoutingData, serializeHosts, EXAMPLE } from "./logic.js";
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
          (h.routes || []).map((r) => ({ network: r.network, nextHop: r.nextHop })),
          (h.interfaces || []).map((i) => ({
            name: i.name,
            ipAddress: i.ipAddress,
            description: i.description || null,
          }))
        )
      )
    );
    const failures = outcomes
      .map((o, i) => (o.status === "rejected" ? { host: draftHosts[i].host, error: o.reason?.message || String(o.reason) } : null))
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
        <p>Paste each host's routing table &amp; interfaces, save to the database, then pick a host to view details.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          <div className="tool-field">
            <div className="tool-label">
              <span>
                Routing tables (draft){" "}
                <span className="tool-hint">@hostname, %interface ip/cidr [- desc], network -&gt; next hop</span>
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
                  {h.routeCount} routes
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
            <>
              <div className="tool-section-title" style={{ marginBottom: 12 }}>
                {selectedDetail.host}
                <span className="tool-hint">
                  saved {formatTimestamp(selectedDetail.updatedAt)}
                </span>
                <button
                  className="tool-btn tool-btn-ghost rm-delete-btn"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? "Deleting…" : "Delete host"}
                </button>
              </div>

              {/* Interfaces Table */}
              <div style={{ marginBottom: 20 }}>
                <h3 className="rm-section-sub-title">Interfaces</h3>
                <div className="tool-table-wrap">
                  <table className="tool-table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>IP Address</th>
                        <th>Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(!selectedDetail.interfaces || selectedDetail.interfaces.length === 0) && (
                        <tr>
                          <td colSpan={3} style={{ color: "var(--muted)" }}>
                            No interfaces for this host.
                          </td>
                        </tr>
                      )}
                      {(selectedDetail.interfaces || []).map((i, idx) => (
                        <tr key={idx}>
                          <td>{i.name}</td>
                          <td>{i.ipAddress}</td>
                          <td>{i.description || ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Routes Table */}
              <div>
                <h3 className="rm-section-sub-title">Network / Next hop</h3>
                <div className="tool-table-wrap">
                  <table className="tool-table">
                    <thead>
                      <tr>
                        <th>Network</th>
                        <th>Next hop</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(!selectedDetail.routes || selectedDetail.routes.length === 0) && (
                        <tr>
                          <td colSpan={2} style={{ color: "var(--muted)" }}>
                            No routes for this host.
                          </td>
                        </tr>
                      )}
                      {(selectedDetail.routes || []).map((r, idx) => (
                        <tr key={idx}>
                          <td>{r.network}</td>
                          <td>{r.nextHop}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
