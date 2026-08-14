import React, { useEffect, useState } from "react";
import "./ipam.css";
import SubnetSearch from "./SubnetSearch.jsx";
import AddSubnetForm from "./AddSubnetForm.jsx";
import {
  formatVlan,
  formatTimestamp,
  utilizationPercent,
  STATUS_LABELS,
  ancestorChain,
  addressesToCsv,
} from "./logic.js";
import {
  listSubnets,
  getSubnet,
  updateSubnet,
  deleteSubnet,
  addAddress,
  updateAddress,
  deleteAddress,
  rescanAddress,
  autodiscoverSubnet,
  listSubnetScans,
  listScanExcludes,
  addScanExclude,
  removeScanExclude,
} from "./api.js";

const STATUS_PILL_CLASS = {
  used: "tool-pill-muted",
  free: "tool-pill-ok",
  reserved: "tool-pill-warn",
};

function UtilizationBar({ subnet }) {
  const total = subnet.totalAddresses || 1;
  const usedPct = Math.min(100, (subnet.usedCount / total) * 100);
  const reservedPct = Math.min(100 - usedPct, (subnet.reservedCount / total) * 100);
  const freePct = Math.min(100 - usedPct - reservedPct, (subnet.freeCount / total) * 100);
  return (
    <div className="ip-util-bar" title={`${utilizationPercent(subnet)}% allocated (used + reserved)`}>
      <div className="ip-util-seg ip-util-used" style={{ width: `${usedPct}%` }} />
      <div className="ip-util-seg ip-util-reserved" style={{ width: `${reservedPct}%` }} />
      <div className="ip-util-seg ip-util-free" style={{ width: `${freePct}%` }} />
    </div>
  );
}

/** Row for one recorded address: view mode + an inline edit mode, plus a delete confirm step. */
const MACHINE_TYPE_LABELS = { physical: "Physical", vm: "VM" };
const ENVIRONMENT_LABELS = { prod: "Prod", test: "Test", dev: "Dev" };

function AddressRow({ subnetId, addr, onUpdated, onError }) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [draft, setDraft] = useState({
    address: addr.address,
    status: addr.status,
    hostname: addr.hostname || "",
    description: addr.description || "",
    team: addr.team || "",
    machineType: addr.machineType || "",
    vmCluster: addr.vmCluster || "",
    environment: addr.environment || "",
    locked: addr.locked || false,
  });

  const startEdit = () => {
    setDraft({
      address: addr.address,
      status: addr.status,
      hostname: addr.hostname || "",
      description: addr.description || "",
      team: addr.team || "",
      machineType: addr.machineType || "",
      vmCluster: addr.vmCluster || "",
      environment: addr.environment || "",
      locked: addr.locked || false,
    });
    setEditing(true);
  };

  const save = async () => {
    onError(null);
    setSaving(true);
    try {
      const updated = await updateAddress(
        subnetId,
        addr.id,
        draft.address.trim(),
        draft.status,
        draft.hostname.trim() || null,
        draft.description.trim() || null,
        draft.team.trim() || null,
        draft.machineType || null,
        draft.machineType === "vm" ? draft.vmCluster.trim() || null : null,
        draft.environment || null,
        draft.locked
      );
      onUpdated(updated);
      setEditing(false);
    } catch (e) {
      onError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    onError(null);
    setSaving(true);
    try {
      const updated = await deleteAddress(subnetId, addr.id);
      onUpdated(updated);
    } catch (e) {
      onError(e.message);
      setSaving(false);
    }
  };

  const rescan = async () => {
    onError(null);
    setRescanning(true);
    try {
      const updated = await rescanAddress(subnetId, addr.id);
      onUpdated(updated);
    } catch (e) {
      onError(e.message);
    } finally {
      setRescanning(false);
    }
  };

  if (editing) {
    return (
      <tr>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.address}
            onChange={(e) => setDraft({ ...draft, address: e.target.value })}
          />
        </td>
        <td>
          <select
            className="tool-input ip-row-input"
            value={draft.status}
            onChange={(e) => setDraft({ ...draft, status: e.target.value })}
          >
            {Object.entries(STATUS_LABELS).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </td>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.hostname}
            onChange={(e) => setDraft({ ...draft, hostname: e.target.value })}
            placeholder="hostname"
          />
        </td>
<td>
          <input
            className="tool-input ip-row-input"
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="description"
          />
        </td>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.team}
            onChange={(e) => setDraft({ ...draft, team: e.target.value })}
            placeholder="team"
          />
        </td>
        <td>
          <select
            className="tool-input ip-row-input"
            value={draft.machineType}
            onChange={(e) => setDraft({ ...draft, machineType: e.target.value, vmCluster: "" })}
          >
            <option value="">—</option>
            {Object.entries(MACHINE_TYPE_LABELS).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </td>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.vmCluster}
            onChange={(e) => setDraft({ ...draft, vmCluster: e.target.value })}
            placeholder="cluster"
            disabled={draft.machineType !== "vm"}
          />
        </td>
        <td>
          <select
            className="tool-input ip-row-input"
            value={draft.environment}
            onChange={(e) => setDraft({ ...draft, environment: e.target.value })}
          >
            <option value="">—</option>
            {Object.entries(ENVIRONMENT_LABELS).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </td>
        <td>
          <input
            type="checkbox"
            checked={draft.locked}
            onChange={(e) => setDraft({ ...draft, locked: e.target.checked })}
          />
        </td>
        <td className="ip-actions-cell">
          <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td className="ip-mono">{addr.address}</td>
      <td>
        <span className={`tool-pill ${STATUS_PILL_CLASS[addr.status]}`}>{STATUS_LABELS[addr.status]}</span>
      </td>
      <td>{addr.hostname || "—"}</td>
      <td>{addr.description || "—"}</td>
      <td>{addr.team || "—"}</td>
      <td>{addr.machineType ? MACHINE_TYPE_LABELS[addr.machineType] : "—"}</td>
      <td>{addr.machineType === "vm" ? addr.vmCluster || "—" : "—"}</td>
      <td>{addr.environment ? ENVIRONMENT_LABELS[addr.environment] : "—"}</td>
      <td>{addr.locked ? "🔒" : "—"}</td>
      <td className="ip-actions-cell">
        {confirmingDelete ? (
          <>
            <button className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger" onClick={remove} disabled={saving}>
              {saving ? "…" : "Confirm"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingDelete(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            {addr.status !== "reserved" && (
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={rescan}
                disabled={rescanning}
              >
                {rescanning ? "…" : "Rescan"}
              </button>
            )}
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEdit}>
              Edit
            </button>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingDelete(true)}>
              Delete
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function AddAddressForm({ subnetId, onAdded, onError }) {
  const [address, setAddress] = useState("");
  const [status, setStatus] = useState("used");
  const [hostname, setHostname] = useState("");
  const [description, setDescription] = useState("");
  const [team, setTeam] = useState("");
  const [machineType, setMachineType] = useState("");
  const [vmCluster, setVmCluster] = useState("");
  const [environment, setEnvironment] = useState("");
  const [locked, setLocked] = useState(false);
  const [adding, setAdding] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!address.trim()) return;
    onError(null);
    setAdding(true);
    try {
      const updated = await addAddress(
        subnetId,
        address.trim(),
        status,
        hostname.trim() || null,
        description.trim() || null,
        team.trim() || null,
        machineType || null,
        machineType === "vm" ? vmCluster.trim() || null : null,
        environment || null,
        locked
      );
      onAdded(updated);
      setAddress("");
      setHostname("");
      setDescription("");
      setStatus("used");
      setTeam("");
      setMachineType("");
      setVmCluster("");
      setEnvironment("");
      setLocked(false);
    } catch (e2) {
      onError(e2.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <form className="ip-add-row" onSubmit={submit}>
      <input
        className="tool-input"
        style={{ maxWidth: 160 }}
        placeholder="10.0.1.10"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
      />
      <select className="tool-input" style={{ maxWidth: 130 }} value={status} onChange={(e) => setStatus(e.target.value)}>
        {Object.entries(STATUS_LABELS).map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <input
        className="tool-input"
        placeholder="hostname (optional)"
        value={hostname}
        onChange={(e) => setHostname(e.target.value)}
      />
      <input
        className="tool-input"
        placeholder="description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <input
        className="tool-input"
        placeholder="team (optional)"
        value={team}
        onChange={(e) => setTeam(e.target.value)}
      />
      <select
        className="tool-input"
        style={{ maxWidth: 110 }}
        value={machineType}
        onChange={(e) => {
          setMachineType(e.target.value);
          setVmCluster("");
        }}
      >
        <option value="">Type…</option>
        {Object.entries(MACHINE_TYPE_LABELS).map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <input
        className="tool-input"
        placeholder="vm cluster"
        value={vmCluster}
        onChange={(e) => setVmCluster(e.target.value)}
        disabled={machineType !== "vm"}
      />
      <select
        className="tool-input"
        style={{ maxWidth: 110 }}
        value={environment}
        onChange={(e) => setEnvironment(e.target.value)}
      >
        <option value="">Env…</option>
        {Object.entries(ENVIRONMENT_LABELS).map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <label className="tool-hint" style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} />
        Locked
      </label>
      <button className="tool-btn tool-btn-primary" type="submit" disabled={adding || !address.trim()}>
        {adding ? "Adding…" : "Add"}
      </button>
    </form>
  );
}

function ScanExcludeManager({ subnetId }) {
  const [excludes, setExcludes] = useState([]);
  const [newAddress, setNewAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    setLoading(true);
    (async () => {
      try {
        const data = await listScanExcludes(subnetId);
        setExcludes(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [subnetId]);

  const addExclude = async (e) => {
    e.preventDefault();
    if (!newAddress.trim()) return;
    setError(null);
    try {
      const updated = await addScanExclude(subnetId, newAddress.trim());
      setExcludes(updated);
      setNewAddress("");
    } catch (e2) {
      setError(e2.message);
    }
  };

  const removeExclude = async (id) => {
    setError(null);
    try {
      const updated = await removeScanExclude(subnetId, id);
      setExcludes(updated);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="ip-scan-excludes">
      <div className="tool-hint">Scan excludes</div>
      {error && <div className="tool-error">{error}</div>}
      {!loading && excludes.length === 0 && (
        <div className="tool-hint">No excluded addresses.</div>
      )}
      {excludes.length > 0 && (
        <ul className="ip-scan-exclude-list">
          {excludes.map((ex) => (
            <li key={ex.id}>
              <span className="ip-mono">{ex.address}</span>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={() => removeExclude(ex.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="ip-add-row" onSubmit={addExclude}>
        <input
          className="tool-input"
          style={{ maxWidth: 160 }}
          placeholder="10.0.1.10"
          value={newAddress}
          onChange={(e) => setNewAddress(e.target.value)}
        />
        <button className="tool-btn tool-btn-primary" type="submit" disabled={!newAddress.trim()}>
          Add
        </button>
      </form>
    </div>
  );
}

function SubnetDetail({ subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet }) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [headerDraft, setHeaderDraft] = useState({
    cidr: subnet.cidr,
    vlan: subnet.vlan ?? "",
    description: subnet.description || "",
  });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [rowError, setRowError] = useState(null);
  const [confirmingScan, setConfirmingScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [lastScan, setLastScan] = useState(null);

  useEffect(() => {
    setConfirmingDelete(false);
    setEditingHeader(false);
    setHeaderError(null);
    setRowError(null);
    setConfirmingScan(false);
    setScanning(false);
    setScanError(null);
    setScanResult(null);
    setLastScan(null);

    (async () => {
      try {
        const scans = await listSubnetScans(subnet.id);
        setLastScan(scans.length > 0 ? scans[0] : null);
      } catch {
        // Scan history is a nice-to-have on this screen — if it fails to
        // load, leave lastScan null rather than surfacing another error.
      }
    })();
  }, [subnet.id]);

  const startEditHeader = () => {
    setHeaderDraft({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "" });
    setHeaderError(null);
    setEditingHeader(true);
  };

  const saveHeader = async () => {
    setHeaderError(null);
    setHeaderSaving(true);
    try {
      const vlan = headerDraft.vlan === "" ? null : Number(headerDraft.vlan);
      const updated = await updateSubnet(subnet.id, headerDraft.cidr.trim(), vlan, headerDraft.description.trim() || null);
      onDetailUpdated(updated);
      setEditingHeader(false);
    } catch (e) {
      setHeaderError(e.message);
    } finally {
      setHeaderSaving(false);
    }
  };

  const runAutodiscover = async () => {
    setScanError(null);
    setScanning(true);
    try {
      const result = await autodiscoverSubnet(subnet.id);
      setScanResult(result);
      // autodiscoverSubnet's response has no startedAt/finishedAt (only
      // scanId/scannedCount/usedCount/freeCount/skippedCount/diff), so
      // hand-building lastScan from it left "last scanned" blank right
      // after a scan. Pull the just-recorded entry from history instead,
      // which has the full record_scan shape including finishedAt.
      try {
        const scans = await listSubnetScans(subnet.id);
        setLastScan(scans.length > 0 ? scans[0] : null);
      } catch {
        // Non-critical — leave lastScan as whatever it was before.
      }
      const refreshed = await getSubnet(subnet.id);
      onDetailUpdated(refreshed);
    } catch (e) {
      setScanError(e.message);
    } finally {
      setScanning(false);
      setConfirmingScan(false);
    }
  };

  const downloadCsv = () => {
    const csv = addressesToCsv(subnet.addresses || []);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${subnet.cidr.replace("/", "_")}-addresses.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const unallocated = subnet.totalAddresses - subnet.recordedCount;
  const ancestors = ancestorChain(subnets, subnet.id);
  const children = subnets.filter((s) => s.parentId === subnet.id);

  return (
    <>
      {ancestors.length > 0 && (
        <div className="ip-breadcrumb">
          {ancestors.map((a) => (
            <React.Fragment key={a.id}>
              <button className="ip-breadcrumb-link" onClick={() => onSelectSubnet(a.id)}>
                {a.cidr}
              </button>
              <span className="ip-breadcrumb-sep">›</span>
            </React.Fragment>
          ))}
          <span>{subnet.cidr}</span>
        </div>
      )}
      <div className="tool-section-title">
        {editingHeader ? (
          <span className="ip-header-edit">
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 160 }}
              value={headerDraft.cidr}
              onChange={(e) => setHeaderDraft({ ...headerDraft, cidr: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 100 }}
              placeholder="VLAN"
              value={headerDraft.vlan}
              onChange={(e) => setHeaderDraft({ ...headerDraft, vlan: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              placeholder="description"
              value={headerDraft.description}
              onChange={(e) => setHeaderDraft({ ...headerDraft, description: e.target.value })}
            />
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={saveHeader} disabled={headerSaving}>
              {headerSaving ? "Saving…" : "Save"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setEditingHeader(false)}
              disabled={headerSaving}
            >
              Cancel
            </button>
          </span>
        ) : (
          <>
            {subnet.cidr}
            <span className="tool-hint">
              {formatVlan(subnet.vlan)} · {subnet.description || "no description"}
              {children.length > 0
                ? ` · ${children.length} nested subnet${children.length !== 1 ? "s" : ""}`
                : ""}{" "}
              · saved {formatTimestamp(subnet.updatedAt)}
              {lastScan && ` · last scanned ${formatTimestamp(lastScan.finishedAt)}`}
            </span>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEditHeader}>
              Edit
            </button>
          </>
        )}
        {!editingHeader && !confirmingDelete && !confirmingScan && (
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setConfirmingScan(true)}
          >
            Autodiscover
          </button>
        )}
        {!editingHeader && !confirmingDelete && !confirmingScan && (
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={downloadCsv}
            disabled={!subnet.addresses || subnet.addresses.length === 0}
          >
            Export CSV
          </button>
        )}
        {!editingHeader && !confirmingScan &&
          (confirmingDelete ? (
            <span className="ip-delete-confirm">
              <span className="tool-hint">Delete subnet "{subnet.cidr}"? This can't be undone.</span>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger"
                onClick={() => {
                  setConfirmingDelete(false);
                  onDelete();
                }}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              className="tool-btn tool-btn-ghost ip-row-btn ip-delete-subnet-btn"
              onClick={() => setConfirmingDelete(true)}
              disabled={deleting}
            >
              Delete subnet
            </button>
          ))}
        {confirmingScan && (
          <span className="ip-delete-confirm">
            <span className="tool-hint">
              Ping every address in {subnet.cidr}? This may take a while.
            </span>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={runAutodiscover}
              disabled={scanning}
            >
              {scanning ? "Scanning…" : "Confirm scan"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingScan(false)}
              disabled={scanning}
            >
              Cancel
            </button>
          </span>
        )}
      </div>
      {headerError && <div className="tool-error">{headerError}</div>}
      {scanError && <div className="tool-error">{scanError}</div>}
      {scanResult && !scanError && (
        <div className="tool-hint ip-scan-summary">
          Scanned {scanResult.scannedCount} · {scanResult.usedCount} used ·{" "}
          {scanResult.freeCount} free · {scanResult.skippedCount} skipped
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setScanResult(null)}
          >
            Dismiss
          </button>
          {scanResult.diff &&
            (scanResult.diff.newlyUsed.length > 0 ||
              scanResult.diff.wentQuiet.length > 0 ||
              scanResult.diff.hostnameChanged.length > 0) && (
                <div className="tool-hint ip-scan-diff">
                {scanResult.diff.newlyUsed.length} new · {scanResult.diff.wentQuiet.length} went
                offline · {scanResult.diff.hostnameChanged.length} hostname change
                {scanResult.diff.hostnameChanged.length === 1 ? "" : "s"}
              </div>
            )}
        </div>
      )}

      <UtilizationBar subnet={subnet} />
      <div className="tool-summary">
        <div className="tool-stat">
          <div className="n">{subnet.totalAddresses.toLocaleString()}</div>
          <div className="l">Total addresses</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.usedCount}</div>
          <div className="l">Used</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.reservedCount}</div>
          <div className="l">Reserved</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.freeCount}</div>
          <div className="l">Free (recorded)</div>
        </div>
        <div className="tool-stat">
          <div className="n">{unallocated.toLocaleString()}</div>
          <div className="l">Not recorded</div>
        </div>
      </div>

      {children.length > 0 && (
        <>
          <h3 className="ip-section-sub-title">
            Nested subnets <span className="tool-hint">{children.length}</span>
          </h3>
          <div className="tool-table-wrap ip-table-wrap-full">
            <table className="tool-table">
              <thead>
                <tr>
                  <th>CIDR</th>
                  <th>VLAN</th>
                  <th>Description</th>
                  <th>Recorded</th>
                </tr>
              </thead>
              <tbody>
                {children.map((c) => (
                  <tr key={c.id} className="ip-child-row" onClick={() => onSelectSubnet(c.id)}>
                    <td className="ip-mono">{c.cidr}</td>
                    <td>{formatVlan(c.vlan)}</td>
                    <td>{c.description || "—"}</td>
                    <td>
                      {c.usedCount}u · {c.reservedCount}r · {c.freeCount}f
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="ip-section-sub-title">Addresses</h3>
      {rowError && <div className="tool-error">{rowError}</div>}
      <AddAddressForm subnetId={subnet.id} onAdded={onDetailUpdated} onError={setRowError} />

      {subnet.addresses.length === 0 ? (
        <div className="tool-empty">No addresses recorded yet — add one above.</div>
      ) : (
        <div className="tool-table-wrap ip-table-wrap-full">
          <table className="tool-table">
            <thead>
              <tr>
                <th>Address</th>
                <th>Status</th>
                <th>Hostname</th>
                <th>Description</th>
                <th>Team</th>
                <th>Type</th>
                <th>VM Cluster</th>
                <th>Env</th>
                <th>Locked</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {subnet.addresses.map((addr) => (
                <AddressRow
                  key={addr.id}
                  subnetId={subnet.id}
                  addr={addr}
                  onUpdated={onDetailUpdated}
                  onError={setRowError}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ScanExcludeManager subnetId={subnet.id} />
    </>
  );
}

export default function Ipam() {
  const [subnets, setSubnets] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const refreshList = async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listSubnets();
      setSubnets(data);
    } catch (e) {
      setListError(e.message);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
  }, []);

  const selectSubnet = async (id) => {
    setSelectedId(id);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await getSubnet(id);
      setSelectedDetail(detail);
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDetailUpdated = (detail) => {
    setSelectedDetail(detail);
    // A CIDR edit (or an address change) can shift the whole nesting tree
    // (this subnet's parent, or other subnets' parents, may have changed) —
    // a full refetch keeps parentId accurate everywhere, not just here.
    refreshList();
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteSubnet(selectedId);
      setSelectedId(null);
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
        <h2>IPAM</h2>
        <p>Track subnets with a VLAN tag, then record individual IP addresses as used, free, or reserved.</p>
      </div>

      <div className="tool-panel">
        <div className="ip-header-row">
          <SubnetSearch subnets={subnets} selectedId={selectedId} onSelect={selectSubnet} />
          <AddSubnetForm
            onCreated={async (created) => {
              await refreshList();
              await selectSubnet(created.id);
            }}
          />
        </div>
        {listError && <div className="tool-error">{listError}</div>}

        <div className="ip-divider" />

        {!selectedId && !listError && (
          <div className="tool-empty">
            {listLoading
              ? "Loading subnets…"
              : subnets.length === 0
              ? "No subnets yet — add one above to get started."
              : "Search above to jump to a subnet by CIDR."}
          </div>
        )}

        {selectedId && detailLoading && <div className="tool-empty">Loading…</div>}

        {selectedId && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}

        {selectedId && !detailLoading && selectedDetail && (
          <SubnetDetail
            subnet={selectedDetail}
            subnets={subnets}
            deleting={deleting}
            onDelete={handleDelete}
            onDetailUpdated={handleDetailUpdated}
            onSelectSubnet={selectSubnet}
          />
        )}
      </div>
    </div>
  );
}