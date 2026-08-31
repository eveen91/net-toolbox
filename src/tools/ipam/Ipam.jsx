import React, { useEffect, useState, useRef } from "react";
import "./ipam.css";
import SubnetSearch from "./SubnetSearch.jsx";
import AddSubnetForm from "./AddSubnetForm.jsx";
import IpamDashboard from "./IpamDashboard.jsx";
import ResubnetReview from "./ResubnetReview.jsx";
import SubnetAllocator from "./SubnetAllocator.jsx";
import DhcpPoolManager from "./DhcpPoolManager.jsx";
import SubnetHeatmap from "./SubnetHeatmap.jsx";
import AddressPopover from "./AddressPopover.jsx";
import TagSelector from "./TagSelector.jsx";
import TagFilterBar from "./TagFilterBar.jsx";
import {
  formatVlan,
  formatTimestamp,
  utilizationPercent,
  ancestorChain,
  addressesToCsv,
} from "./logic.js";
import {
  listSubnets,
  getSubnet,
  updateSubnet,
  deleteSubnet,
  startAutodiscoverJob,
  autodiscoverStreamUrl,
  getActiveAutodiscoverJob,
  listSubnetScans,
  listScanExcludes,
  addScanExclude,
  removeScanExclude,
  getIpamSettings,
  updateIpamSettings,
  fetchTags,
  fetchSubnetTags,
  addSubnetTag,
  removeSubnetTag,
  fetchAddressTags,
  addAddressTag,
  removeAddressTag,
  fetchSubnetAllocation,
} from "./api.js";

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

function SubnetDetail({ subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet, onAddressSelected, highlightedAddressId, tags, subnetTagIds = [], onTagChange, onTagCreated, addressTagIds = {}, onAddressTagChange }) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [headerDraft, setHeaderDraft] = useState({
    cidr: subnet.cidr,
    vlan: subnet.vlan ?? "",
    description: subnet.description || "",
  });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [confirmingScan, setConfirmingScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [lastScan, setLastScan] = useState(null);
  const [scanProgress, setScanProgress] = useState(null);
  const [dhcpPools, setDhcpPools] = useState([]);
  const eventSourceRef = useRef(null);
  const heatmapStageRef = useRef(null);
  const popoverOriginRef = useRef(null);
  const [popoverIp, setPopoverIp] = useState(null);
  const [popoverCoords, setPopoverCoords] = useState(null);
  const [popoverPlacement, setPopoverPlacement] = useState("below");
  const [heatmapPage, setHeatmapPage] = useState(0);


  useEffect(() => {
    if (eventSourceRef.current !== null) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConfirmingDelete(false);
    setEditingHeader(false);
    setHeaderError(null);
    setConfirmingScan(false);
    setScanning(false);
    setScanError(null);
    setScanResult(null);
    setLastScan(null);
    setScanProgress(null);
    setHeatmapPage(0);

    setDhcpPools([]);

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
    setScanProgress({ completed: 0, total: 0 });
    try {
      const { jobId } = await startAutodiscoverJob(subnet.id);
      const es = new EventSource(autodiscoverStreamUrl(subnet.id, jobId));
      eventSourceRef.current = es;
      let settled = false;
      es.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        setScanProgress({ completed: payload.completed, total: payload.total });
        if (payload.status === "done") {
          settled = true;
          setScanResult(payload.result);
          es.close();
          eventSourceRef.current = null;
          // payload.result has no finishedAt (only
          // scannedCount/usedCount/freeCount/skippedCount/diff), so
          // hand-building lastScan from it leaves "last scanned" blank.
          // Pull the just-recorded entry from history instead, which has
          // the full record_scan shape including finishedAt.
          try {
            const scans = await listSubnetScans(subnet.id);
            setLastScan(scans.length > 0 ? scans[0] : null);
          } catch {
            // Non-critical — leave lastScan as whatever it was before.
          }
          const refreshed = await getSubnet(subnet.id);
          onDetailUpdated(refreshed);
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        } else if (payload.status === "error") {
          settled = true;
          setScanError(payload.error || "Scan failed");
          es.close();
          eventSourceRef.current = null;
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        }
      };
      es.onerror = () => {
        if (settled) return;
        setScanError("Lost connection to the scan progress stream.");
        es.close();
        eventSourceRef.current = null;
        setScanning(false);
        setConfirmingScan(false);
        setScanProgress(null);
      };
    } catch (e) {
      setScanError(e.message);
      setScanning(false);
      setConfirmingScan(false);
      setScanProgress(null);
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
  const heatmapSubnet = React.useMemo(
    () => ({ ...subnet, dhcpPools }),
    [subnet, dhcpPools]
  );
  const popoverAddress =
    subnet.addresses.find((item) => item.address === popoverIp) || null;

  const closePopover = (expectedIp) => {
    if (expectedIp && popoverIp !== expectedIp) return;
    const origin = popoverOriginRef.current;
    setPopoverIp(null);
    setPopoverCoords(null);
    requestAnimationFrame(() => origin?.focus());
  };

  const handleHeatmapCellClick = (ip, cellElement) => {
    const stage = heatmapStageRef.current;
    if (!stage || !cellElement) return;

    const cellRect = cellElement.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const rawX = cellRect.left - stageRect.left + cellRect.width / 2;
    const popoverWidth = Math.min(380, stageRect.width - 16);
    const halfWidth = popoverWidth / 2;
    const x = Math.max(halfWidth + 8, Math.min(rawX, stageRect.width - halfWidth - 8));
    const estimatedHeight = Math.min(560, window.innerHeight * 0.7);
    const openAbove =
      cellRect.bottom + estimatedHeight > window.innerHeight &&
      cellRect.top > window.innerHeight / 2;

    setPopoverIp(ip);
    popoverOriginRef.current = cellElement;
    const address = subnet.addresses.find((item) => item.address === ip);
    if (address) onAddressSelected?.(address.id);
    setPopoverPlacement(openAbove ? "above" : "below");
    setPopoverCoords({
      x,
      y: openAbove ? cellRect.top - stageRect.top : cellRect.bottom - stageRect.top,
      arrowOffset: rawX - x,
    });
  };

  useEffect(() => {
    closePopover();
  }, [subnet.id]);

  useEffect(() => {
    const handleResize = () => closePopover();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (!highlightedAddressId) return undefined;

    const frameId = requestAnimationFrame(() => {
      const stage = heatmapStageRef.current;
      const cellElement = stage?.querySelector(`[data-address-id="${highlightedAddressId}"]`);
      if (!cellElement) return;
      cellElement.scrollIntoView({ behavior: "smooth", block: "center" });
      cellElement.focus({ preventScroll: true });
      const ip = cellElement.dataset.ip;
      if (ip) {
        onAddressSelected?.(highlightedAddressId);
        handleHeatmapCellClick(ip, cellElement);
      }
    });

    return () => cancelAnimationFrame(frameId);
  }, [heatmapPage, highlightedAddressId, subnet.id]);

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
          <>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingScan(true)}
            >
              Autodiscover
            </button>
            <ScanStatusIcon subnetId={subnet.id} />
          </>
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
              {scanning
                ? scanProgress && scanProgress.total > 0
                  ? `Scanning ${scanProgress.completed}/${scanProgress.total}…`
                  : "Starting…"
                : "Confirm scan"}
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

      <div className="ip-heatmap-stage" ref={heatmapStageRef}>
        <SubnetHeatmap
          subnet={heatmapSubnet}
          subnets={subnets}
          onCellClick={handleHeatmapCellClick}
          page={heatmapPage}
          onPageChange={setHeatmapPage}
          focusedAddressId={highlightedAddressId}
        />
        {popoverIp && popoverCoords && (
          <AddressPopover
            ip={popoverIp}
            address={popoverAddress}
            subnetId={subnet.id}
            coords={popoverCoords}
            placement={popoverPlacement}
            onClose={closePopover}
            onUpdated={onDetailUpdated}
            tags={tags}
            addressTags={popoverAddress ? addressTagIds[popoverAddress.id] || [] : []}
            onAddressTagChange={onAddressTagChange}
            onTagCreated={onTagCreated}
          />
        )}
      </div>

      <h3 className="ip-section-sub-title">DHCP Pools</h3>
      <DhcpPoolManager
        subnetId={subnet.id}
        subnets={subnets}
        onPoolsChanged={setDhcpPools}
      />

      <h3 className="ip-section-sub-title">Tags</h3>
      <TagSelector
        value={subnetTagIds.map((t) => t.id)}
        onChange={(newIds) => onTagChange(newIds)}
        allTags={tags}
        placeholder="Add tags to this subnet"
        onTagCreated={onTagCreated}
      />

      <ScanExcludeManager subnetId={subnet.id} />
    </>
  );
}

function ScanStatusIcon({ subnetId }) {
  const [scanning, setScanning] = useState(false);
  const [addresses, setAddresses] = useState([]);
  const [jobId, setJobId] = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const checkActive = async () => {
      try {
        const result = await getActiveAutodiscoverJob(subnetId);
        if (cancelled) return;
        if (result.jobId != null) {
          if (esRef.current == null) {
            setScanning(true);
            setJobId(result.jobId);
            const es = new EventSource(autodiscoverStreamUrl(subnetId, result.jobId));
            esRef.current = es;
            es.onmessage = (event) => {
              const payload = JSON.parse(event.data);
              setAddresses(payload.addresses || []);
              if (payload.status === "done" || payload.status === "error") {
                es.close();
                esRef.current = null;
                setScanning(false);
              }
            };
          }
        } else {
          setScanning(false);
        }
      } catch {
        // Best-effort polling — a failed check just waits for the next tick.
      }
    };

    checkActive();
    const intervalId = setInterval(checkActive, 5000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      if (esRef.current !== null) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [subnetId]);

  return (
    <span className="ip-scan-status-icon-wrap">
      <span className={`ip-scan-status-icon ${scanning ? "scanning" : "idle"}`} />
      {addresses.length > 0 && (
        <div className="ip-scan-status-popover">
          <div className="tool-hint">
            {scanning ? "Scan in progress" : "Last scan"}
          </div>
          <div className="ip-scan-status-list">
            {addresses.map((a) => (
              <div key={a.address} className="ip-scan-status-row">
                <span className="ip-scan-status-addr">{a.address}</span>
                <span className={`ip-scan-status-badge ${a.status}`}>
                  {a.status === "pending"
                    ? "pending"
                    : a.status === "in_progress"
                    ? "scanning…"
                    : a.alive
                    ? "used"
                    : "free"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}

export default function Ipam() {
  const [subnets, setSubnets] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);
  const [viewMode, setViewMode] = useState("search"); // "search" | "dashboard" | "resubnet"

  const [selectedId, setSelectedId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [highlightedAddressId, setHighlightedAddressId] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [scanConcurrencyLimit, setScanConcurrencyLimit] = useState(null);
  const [concurrencyBounds, setConcurrencyBounds] = useState({ min: 1, max: 256 });
  const [settingsError, setSettingsError] = useState(null);
  const [settingsSaving, setSettingsSaving] = useState(false);

  const [allTags, setAllTags] = useState([]);
  const [tagError, setTagError] = useState(null);
  const [selectedTagIds, setSelectedTagIds] = useState([]);
  const [subnetTagIds, setSubnetTagIds] = useState({});
  const [addressTagIds, setAddressTagIds] = useState({});
  const addressTagCacheRef = useRef(new Set());
  const addressTagRequestsRef = useRef(new Map());
  const selectionGenerationRef = useRef(0);

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

  useEffect(() => {
    setTagError(null);
    fetchTags()
      .then((tags) => setAllTags(tags))
      .catch((e) => setTagError(e.message))
  }, []);

  const loadSubnetTags = async (subnetId) => {
    try {
      const tags = await fetchSubnetTags(subnetId);
      setSubnetTagIds((prev) => ({ ...prev, [subnetId]: tags }));
    } catch {
      // best-effort
    }
  };

  const loadAddressTags = async (addressId) => {
    if (addressTagCacheRef.current.has(addressId)) {
      return addressTagIds[addressId] || [];
    }
    if (addressTagRequestsRef.current.has(addressId)) {
      return addressTagRequestsRef.current.get(addressId);
    }

    const request = fetchAddressTags(addressId)
      .then((tags) => {
        addressTagCacheRef.current.add(addressId);
        setAddressTagIds((prev) => ({ ...prev, [addressId]: tags }));
        return tags;
      })
      .catch(() => [])
      .finally(() => addressTagRequestsRef.current.delete(addressId));
    addressTagRequestsRef.current.set(addressId, request);

    return request;
  };

  const handleTagChange = async (subnetId, newTagIds) => {
    const current = subnetTagIds[subnetId] || [];
    const currentIds = current.map((t) => t.id);
    const toAdd = newTagIds.filter((id) => !currentIds.includes(id));
    const toRemove = currentIds.filter((id) => !newTagIds.includes(id));

    for (const tagId of toAdd) {
      await addSubnetTag(subnetId, tagId);
    }
    for (const tagId of toRemove) {
      await removeSubnetTag(subnetId, tagId);
    }
    await loadSubnetTags(subnetId);
  };

  const handleAddressTagChange = async (addressId, newTagIds) => {
    const current = addressTagIds[addressId] || [];
    const currentIds = current.map((t) => t.id);
    const toAdd = newTagIds.filter((id) => !currentIds.includes(id));
    const toRemove = currentIds.filter((id) => !newTagIds.includes(id));

    for (const tagId of toAdd) {
      await addAddressTag(addressId, tagId);
    }
    for (const tagId of toRemove) {
      await removeAddressTag(addressId, tagId);
    }
    addressTagCacheRef.current.delete(addressId);
    setAddressTagIds((prev) => {
      const next = { ...prev };
      delete next[addressId];
      return next;
    });
    await loadAddressTags(addressId);
  };

  const handleFilterTagRemove = (tagId) => {
    setSelectedTagIds((prev) => prev.filter((id) => id !== tagId));
  };

  const handleTagCreated = (tag) => {
    setAllTags((previous) =>
      previous.some((item) => item.id === tag.id) ? previous : [...previous, tag]
    );
  };

  const loadSettings = async () => {
    setSettingsError(null);
    try {
      const result = await getIpamSettings();
      setScanConcurrencyLimit(result.scanConcurrencyLimit);
      setConcurrencyBounds({ min: result.scanConcurrencyMin, max: result.scanConcurrencyMax });
    } catch (e) {
      setSettingsError(e.message);
    }
  };

  const openSettings = () => {
    setShowSettings(true);
    loadSettings();
  };

  const saveSettings = async () => {
    setSettingsError(null);
    setSettingsSaving(true);
    try {
      await updateIpamSettings(Number(scanConcurrencyLimit));
      setShowSettings(false);
    } catch (e) {
      setSettingsError(e.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  const selectSubnet = async (id, targetAddressId = null) => {
    const generation = selectionGenerationRef.current + 1;
    selectionGenerationRef.current = generation;
    setSelectedId(id);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    setHighlightedAddressId(targetAddressId || null);
    try {
      const detail = await getSubnet(id);
      if (selectionGenerationRef.current !== generation) return;
      setSelectedDetail(detail);
      setDetailLoading(false);
      // Tags are independent from the detail payload. Address tags load only
      // when a recorded address is opened in the heatmap.
      void loadSubnetTags(id);
    } catch (e) {
      if (selectionGenerationRef.current !== generation) return;
      setDetailError(e.message);
    } finally {
      if (selectionGenerationRef.current === generation) setDetailLoading(false);
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
          <SubnetSearch
            subnets={subnets}
            selectedId={selectedId}
            tags={allTags}
            selectedTagIds={selectedTagIds}
            onTagFilterChange={setSelectedTagIds}
            onSelect={(id, addressId) => {
              setViewMode("search");
              selectSubnet(id, addressId);
            }}
          />
          <AddSubnetForm
            onCreated={async (created) => {
              await refreshList();
              await selectSubnet(created.id);
            }}
          />
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setViewMode(viewMode === "dashboard" ? "search" : "dashboard")}
          >
            {viewMode === "dashboard" ? "Back to search" : "Dashboard"}
          </button>
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setViewMode(viewMode === "resubnet" ? "search" : "resubnet")}
          >
            {viewMode === "resubnet" ? "Back to search" : "Resubnet"}
          </button>
          <button
            className="tool-btn tool-btn-ghost ip-row-btn"
            onClick={() => setViewMode(viewMode === "allocator" ? "search" : "allocator")}
          >
            {viewMode === "allocator" ? "Back to search" : "Allocator"}
          </button>
          <div className="ip-settings-wrap">
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={openSettings}
              title="Autodiscovery settings"
            >
              ⚙
            </button>
            {showSettings && (
              <div className="tool-popover ip-settings-popover">
                <div className="tool-hint">Autodiscovery settings</div>
                {scanConcurrencyLimit === null ? (
                  <div className="tool-hint">Loading…</div>
                ) : (
                  <>
                    <label className="tool-hint">
                      Simultaneous scans (hosts pinged at once)
                    </label>
                    <input
                      className="tool-input"
                      type="number"
                      min={concurrencyBounds.min}
                      max={concurrencyBounds.max}
                      value={scanConcurrencyLimit}
                      onChange={(e) => setScanConcurrencyLimit(e.target.value)}
                    />
                    <div className="tool-hint">
                      Range: {concurrencyBounds.min}–{concurrencyBounds.max}
                    </div>
                    {settingsError && <div className="tool-error">{settingsError}</div>}
                    <div className="ip-settings-actions">
                      <button
                        className="tool-btn tool-btn-primary"
                        onClick={saveSettings}
                        disabled={settingsSaving}
                      >
                        {settingsSaving ? "Saving…" : "Save"}
                      </button>
                      <button
                        className="tool-btn tool-btn-ghost"
                        onClick={() => setShowSettings(false)}
                        disabled={settingsSaving}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {selectedTagIds.length > 0 && (
          <TagFilterBar
            tags={allTags.filter((t) => selectedTagIds.includes(t.id))}
            onRemove={handleFilterTagRemove}
          />
        )}

        {viewMode === "search" && (
          <>
            {listError && <div className="tool-error">{listError}</div>}
            {tagError && <div className="tool-error">Unable to load tags: {tagError}</div>}

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
                tags={allTags}
                subnetTagIds={subnetTagIds[selectedId] || []}
                onTagChange={(newIds) => handleTagChange(selectedId, newIds)}
                onTagCreated={handleTagCreated}
                addressTagIds={addressTagIds}
                onAddressTagChange={handleAddressTagChange}
                deleting={deleting}
                onDelete={handleDelete}
                onDetailUpdated={handleDetailUpdated}
                onSelectSubnet={selectSubnet}
                onAddressSelected={loadAddressTags}
                highlightedAddressId={highlightedAddressId}
              />
            )}
          </>
        )}

        {viewMode === "dashboard" && (
          <IpamDashboard
            onSelectSubnet={(id) => {
              setViewMode("search");
              selectSubnet(id);
            }}
            tags={allTags}
          />
        )}

        {viewMode === "resubnet" && (
          <ResubnetReview onMoved={refreshList} />
        )}

        {viewMode === "allocator" && (
          <SubnetAllocator
            subnets={subnets}
            onCreate={(created) => {
              refreshList();
              setViewMode("search");
              setTimeout(() => selectSubnet(created.id), 50);
            }}
          />
        )}
      </div>
    </div>
  );
}
