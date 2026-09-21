import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AddressPopover from "./AddressPopover.jsx";
import AddressTable from "./AddressTable.jsx";
import AuditTimeline from "./AuditTimeline.jsx";
import DhcpPoolManager from "./DhcpPoolManager.jsx";
import ScanExcludeManager from "./ScanExcludeManager.jsx";
import ScanStatusIcon from "./ScanStatusIcon.jsx";
import SubnetHeatmap from "./SubnetHeatmap.jsx";
import TagSelector from "./TagSelector.jsx";
import { getAllSubnetAddresses, updateSubnet } from "./api.js";
import { addressesToCsv, ancestorChain, formatTimestamp, formatVlan, utilizationPercent } from "./logic.js";
import { useIpamScan } from "./hooks/useIpamScan.js";

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

export default function SubnetDetail({
  subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet,
  onAddressSelected, highlightedAddressId, tags, subnetTagIds = [], onTagChange,
  onTagCreated, addressTagIds = {}, onAddressTagChange,
}) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [headerDraft, setHeaderDraft] = useState({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "" });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [dhcpPools, setDhcpPools] = useState([]);
  const [popoverIp, setPopoverIp] = useState(null);
  const [popoverCoords, setPopoverCoords] = useState(null);
  const [popoverPlacement, setPopoverPlacement] = useState("below");
  const [heatmapPage, setHeatmapPage] = useState(0);
  const [heatmapAddresses, setHeatmapAddresses] = useState([]);
  const [heatmapError, setHeatmapError] = useState(null);
  const [focusedAddress, setFocusedAddress] = useState(null);
  const [addressRefreshKey, setAddressRefreshKey] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [detailSection, setDetailSection] = useState("inventory");
  const heatmapStageRef = useRef(null);
  const popoverOriginRef = useRef(null);
  const {
    confirmingScan, scanning, scanError, scanResult, lastScan, scanProgress,
    setConfirmingScan, setScanResult, runAutodiscover,
  } = useIpamScan(subnet.id, onDetailUpdated);

  useEffect(() => {
    setConfirmingDelete(false);
    setEditingHeader(false);
    setHeaderError(null);
    setHeatmapPage(0);
    setHeatmapAddresses([]);
    setHeatmapError(null);
    setFocusedAddress(null);
    setExportError(null);
    setDetailSection("inventory");
    setAddressRefreshKey((key) => key + 1);
    setDhcpPools([]);
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
    } catch (error) {
      setHeaderError(error.message);
    } finally {
      setHeaderSaving(false);
    }
  };

  const downloadCsv = async () => {
    setExportError(null);
    setExporting(true);
    try {
      const addresses = await getAllSubnetAddresses(subnet.id, { sort: "address", direction: "asc" });
      const blob = new Blob([addressesToCsv(addresses)], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${subnet.cidr.replace("/", "_")}-addresses.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(error.message);
    } finally {
      setExporting(false);
    }
  };

  const ancestors = ancestorChain(subnets, subnet.id);
  const children = subnets.filter((item) => item.parentId === subnet.id);
  const unallocated = subnet.totalAddresses - subnet.recordedCount;
  const heatmapSubnet = useMemo(() => ({ ...subnet, dhcpPools }), [subnet, dhcpPools]);
  const popoverAddress = heatmapAddresses.find((item) => item.address === popoverIp) || null;

  const handleAddressesLoaded = useCallback((addresses, error) => {
    setHeatmapAddresses(addresses);
    setHeatmapError(error ? error.message : null);
  }, []);

  const handleAddressMutation = (updated) => {
    setAddressRefreshKey((key) => key + 1);
    onDetailUpdated(updated);
  };

  const closePopover = useCallback((expectedIp) => {
    if (expectedIp && popoverIp !== expectedIp) return;
    const origin = popoverOriginRef.current;
    setPopoverIp(null);
    setPopoverCoords(null);
    requestAnimationFrame(() => origin?.focus());
  }, [popoverIp]);

  const handleHeatmapCellClick = useCallback((ip, cellElement) => {
    const stage = heatmapStageRef.current;
    if (!stage || !cellElement) return;
    const cellRect = cellElement.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const rawX = cellRect.left - stageRect.left + cellRect.width / 2;
    const popoverWidth = Math.min(380, stageRect.width - 16);
    const halfWidth = popoverWidth / 2;
    const x = Math.max(halfWidth + 8, Math.min(rawX, stageRect.width - halfWidth - 8));
    const estimatedHeight = Math.min(560, window.innerHeight * 0.7);
    const openAbove = cellRect.bottom + estimatedHeight > window.innerHeight && cellRect.top > window.innerHeight / 2;
    setPopoverIp(ip);
    popoverOriginRef.current = cellElement;
    const address = heatmapAddresses.find((item) => item.address === ip);
    if (address) onAddressSelected?.(address.id);
    setPopoverPlacement(openAbove ? "above" : "below");
    setPopoverCoords({ x, y: openAbove ? cellRect.top - stageRect.top : cellRect.bottom - stageRect.top, arrowOffset: rawX - x });
  }, [heatmapAddresses, onAddressSelected]);

  useEffect(() => {
    closePopover();
  }, [subnet.id]);

  useEffect(() => {
    const handleResize = () => closePopover();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [closePopover]);

  useEffect(() => {
    const targetAddress = focusedAddress || heatmapAddresses.find((address) => address.id === highlightedAddressId);
    if (!targetAddress) return undefined;
    const frameId = requestAnimationFrame(() => {
      const cellElement = heatmapStageRef.current?.querySelector(`[data-address-id="${targetAddress.id}"]`);
      if (!cellElement) return;
      cellElement.scrollIntoView({ behavior: "smooth", block: "center" });
      cellElement.focus({ preventScroll: true });
      onAddressSelected?.(targetAddress.id);
      handleHeatmapCellClick(targetAddress.address, cellElement);
      if (focusedAddress) setFocusedAddress(null);
    });
    return () => cancelAnimationFrame(frameId);
  }, [focusedAddress, handleHeatmapCellClick, heatmapAddresses, heatmapPage, highlightedAddressId, onAddressSelected, subnet.id]);

  return (
    <>
      {ancestors.length > 0 && (
        <div className="ip-breadcrumb">
          {ancestors.map((ancestor) => (
            <React.Fragment key={ancestor.id}>
              <button className="ip-breadcrumb-link" onClick={() => onSelectSubnet(ancestor.id)}>{ancestor.cidr}</button>
              <span className="ip-breadcrumb-sep">›</span>
            </React.Fragment>
          ))}
          <span>{subnet.cidr}</span>
        </div>
      )}
      <div className="tool-section-title">
        {editingHeader ? (
          <span className="ip-header-edit">
            <input className="tool-input ip-row-input" style={{ maxWidth: 160 }} aria-label="Subnet CIDR" value={headerDraft.cidr} onChange={(event) => setHeaderDraft({ ...headerDraft, cidr: event.target.value })} />
            <input className="tool-input ip-row-input" style={{ maxWidth: 100 }} placeholder="VLAN" aria-label="VLAN" value={headerDraft.vlan} onChange={(event) => setHeaderDraft({ ...headerDraft, vlan: event.target.value })} />
            <input className="tool-input ip-row-input" placeholder="description" aria-label="Description" value={headerDraft.description} onChange={(event) => setHeaderDraft({ ...headerDraft, description: event.target.value })} />
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={saveHeader} disabled={headerSaving}>{headerSaving ? "Saving…" : "Save"}</button>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setEditingHeader(false)} disabled={headerSaving}>Cancel</button>
          </span>
        ) : (
          <>
            {subnet.cidr}
            <span className="tool-hint">
              {formatVlan(subnet.vlan)} · {subnet.description || "no description"}
              {children.length > 0 ? ` · ${children.length} nested subnet${children.length !== 1 ? "s" : ""}` : ""}{" "}
              · saved {formatTimestamp(subnet.updatedAt)}
              {lastScan && ` · last scanned ${formatTimestamp(lastScan.finishedAt)}`}
            </span>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEditHeader}>Edit</button>
          </>
        )}
        {!editingHeader && !confirmingDelete && !confirmingScan && (
          <>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingScan(true)}>Autodiscover</button>
            <ScanStatusIcon subnetId={subnet.id} />
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={downloadCsv} disabled={exporting || subnet.recordedCount === 0}>{exporting ? "Exporting…" : "Export CSV"}</button>
          </>
        )}
        {!editingHeader && !confirmingScan && (confirmingDelete ? (
          <span className="ip-delete-confirm">
            <span className="tool-hint">Delete subnet "{subnet.cidr}"? This can't be undone.</span>
            <button className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger" onClick={() => { setConfirmingDelete(false); onDelete(); }} disabled={deleting}>{deleting ? "Deleting…" : "Confirm delete"}</button>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingDelete(false)} disabled={deleting}>Cancel</button>
          </span>
        ) : (
          <button className="tool-btn tool-btn-ghost ip-row-btn ip-delete-subnet-btn" onClick={() => setConfirmingDelete(true)} disabled={deleting}>Delete subnet</button>
        ))}
        {confirmingScan && (
          <span className="ip-delete-confirm">
            <span className="tool-hint">Ping every address in {subnet.cidr}? This may take a while.</span>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={runAutodiscover} disabled={scanning}>
              {scanning ? scanProgress && scanProgress.total > 0 ? `Scanning ${scanProgress.completed}/${scanProgress.total}…` : "Starting…" : "Confirm scan"}
            </button>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingScan(false)} disabled={scanning}>Cancel</button>
          </span>
        )}
      </div>
      {headerError && <div className="tool-error">{headerError}</div>}
      {scanError && <div className="tool-error">{scanError}</div>}
      {exportError && <div className="tool-error" role="alert">CSV export failed: {exportError}</div>}
      {scanResult && !scanError && (
        <div className="tool-hint ip-scan-summary">
          Scanned {scanResult.scannedCount} · {scanResult.usedCount} used · {scanResult.freeCount} free · {scanResult.skippedCount} skipped
          <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setScanResult(null)}>Dismiss</button>
          {scanResult.diff && (scanResult.diff.newlyUsed.length > 0 || scanResult.diff.wentQuiet.length > 0 || scanResult.diff.hostnameChanged.length > 0) && (
            <div className="tool-hint ip-scan-diff">{scanResult.diff.newlyUsed.length} new · {scanResult.diff.wentQuiet.length} went offline · {scanResult.diff.hostnameChanged.length} hostname change{scanResult.diff.hostnameChanged.length === 1 ? "" : "s"}</div>
          )}
        </div>
      )}

      <div className="ip-detail-tabs" role="tablist" aria-label="Subnet detail sections">
        <button type="button" role="tab" aria-selected={detailSection === "inventory"} aria-controls="ip-subnet-inventory" className={detailSection === "inventory" ? "active" : ""} onClick={() => setDetailSection("inventory")}>Inventory</button>
        <button type="button" role="tab" aria-selected={detailSection === "history"} aria-controls="ip-subnet-history" className={detailSection === "history" ? "active" : ""} onClick={() => setDetailSection("history")}>History</button>
      </div>

      {detailSection === "history" ? (
        <div id="ip-subnet-history" role="tabpanel">
          <AuditTimeline key={subnet.id} subnetId={subnet.id} title={`${subnet.cidr} history`} description="Changes recorded for this subnet and its addresses." showTarget />
        </div>
      ) : <div id="ip-subnet-inventory" role="tabpanel">
      <UtilizationBar subnet={subnet} />
      <div className="tool-summary">
        <div className="tool-stat"><div className="n">{subnet.totalAddresses.toLocaleString()}</div><div className="l">Total addresses</div></div>
        <div className="tool-stat"><div className="n">{subnet.usedCount}</div><div className="l">Used</div></div>
        <div className="tool-stat"><div className="n">{subnet.reservedCount}</div><div className="l">Reserved</div></div>
        <div className="tool-stat"><div className="n">{subnet.freeCount}</div><div className="l">Free (recorded)</div></div>
        <div className="tool-stat"><div className="n">{unallocated.toLocaleString()}</div><div className="l">Not recorded</div></div>
      </div>

      {children.length > 0 && (
        <>
          <h3 className="ip-section-sub-title">Nested subnets <span className="tool-hint">{children.length}</span></h3>
          <div className="tool-table-wrap ip-table-wrap-full">
            <table className="tool-table">
              <thead><tr><th>CIDR</th><th>VLAN</th><th>Description</th><th>Recorded</th></tr></thead>
              <tbody>{children.map((child) => (
                <tr key={child.id} className="ip-child-row" onClick={() => onSelectSubnet(child.id)}>
                  <td className="ip-mono">{child.cidr}</td><td>{formatVlan(child.vlan)}</td><td>{child.description || "—"}</td>
                  <td>{child.usedCount}u · {child.reservedCount}r · {child.freeCount}f</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}

      <div className="ip-heatmap-stage" ref={heatmapStageRef}>
        <SubnetHeatmap subnet={heatmapSubnet} subnets={subnets} onCellClick={handleHeatmapCellClick} page={heatmapPage} onPageChange={setHeatmapPage} focusedAddress={focusedAddress} addresses={heatmapAddresses} onAddressesLoaded={handleAddressesLoaded} refreshKey={addressRefreshKey} />
        {heatmapError && <div className="tool-error" role="alert">Heatmap failed to load: {heatmapError}</div>}
        {popoverIp && popoverCoords && (
          <AddressPopover ip={popoverIp} address={popoverAddress} subnetId={subnet.id} coords={popoverCoords} placement={popoverPlacement} onClose={closePopover} onUpdated={handleAddressMutation} tags={tags} addressTags={popoverAddress ? addressTagIds[popoverAddress.id] || [] : []} onAddressTagChange={onAddressTagChange} onTagCreated={onTagCreated} />
        )}
      </div>

      <AddressTable subnetId={subnet.id} refreshKey={addressRefreshKey} highlightedAddressId={highlightedAddressId} onAddressOpen={(address) => { setFocusedAddress(address); setPopoverIp(null); setPopoverCoords(null); }} />
      <h3 className="ip-section-sub-title">DHCP Pools</h3>
      <DhcpPoolManager subnetId={subnet.id} subnets={subnets} onPoolsChanged={setDhcpPools} />
      <h3 className="ip-section-sub-title">Tags</h3>
      <TagSelector value={subnetTagIds.map((tag) => tag.id)} onChange={onTagChange} allTags={tags} placeholder="Add tags to this subnet" onTagCreated={onTagCreated} />
      <ScanExcludeManager subnetId={subnet.id} />
      </div>}
    </>
  );
}
