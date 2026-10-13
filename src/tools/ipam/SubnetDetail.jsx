import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MoveSubnetForm from "./MoveSubnetForm.jsx";
import AddressPopover from "./AddressPopover.jsx";
import AllocateNextAddressForm from "./AllocateNextAddressForm.jsx";
import AddressTable from "./AddressTable.jsx";
import AuditTimeline from "./AuditTimeline.jsx";
import DhcpPoolManager from "./DhcpPoolManager.jsx";
import RangeReservationManager from "./RangeReservationManager.jsx";
import ScanExcludeManager from "./ScanExcludeManager.jsx";
import ScanStatusIcon from "./ScanStatusIcon.jsx";
import SubnetHeatmap from "./SubnetHeatmap.jsx";
import TagSelector from "./TagSelector.jsx";
import { allocateNextAddress, getAllSubnetAddresses, getSubnet, getSubnetAddresses, updateSubnet } from "./api.js";
import { addressesToCsv, ancestorChain, formatTimestamp, formatVlan, shouldCloseAddressPopover, utilizationPercent } from "./logic.js";
import ViewTabs from "../../components/ViewTabs.jsx";
import { canLeaveWorkspace } from "../../components/navigation.js";
import useUnsavedChanges from "../../components/useUnsavedChanges.js";
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
  subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet, onMoved,
  onAddressSelected, highlightedAddressId, tags, subnetTagIds = [], onTagChange,
  onTagCreated, addressTagIds = {}, onAddressTagChange, canWrite = true, canScan = true, permissions = { admin: true },
}) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [archiveReason, setArchiveReason] = useState("");
  const [headerDraft, setHeaderDraft] = useState({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "", updatedAt: subnet.updatedAt });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [dhcpPools, setDhcpPools] = useState([]);
  const [rangeReservations, setRangeReservations] = useState([]);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [popoverIp, setPopoverIp] = useState(null);
  const [heatmapPage, setHeatmapPage] = useState(0);
  const [heatmapAddresses, setHeatmapAddresses] = useState([]);
  const [heatmapError, setHeatmapError] = useState(null);
  const [focusedAddress, setFocusedAddress] = useState(null);
  const [addressRefreshKey, setAddressRefreshKey] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [detailSection, setDetailSection] = useState("inventory");
  const [inventoryView, setInventoryView] = useState("heatmap");
  const [allocatingNext, setAllocatingNext] = useState(false);
  const heatmapStageRef = useRef(null);
  const popoverOriginRef = useRef(null);
  const addressSelectionEpoch = useRef(0);
  useEffect(() => () => { addressSelectionEpoch.current += 1; }, []);
  const handleScanCompleted = useCallback(() => {
    setAddressRefreshKey((key) => key + 1);
  }, []);
  const {
    confirmingScan, scanning, scanError, scanResult, lastScan, scanProgress,
    setConfirmingScan, setScanResult, runAutodiscover,
  } = useIpamScan(subnet.id, onDetailUpdated, handleScanCompleted);

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
    setInventoryView("heatmap");
    setAddressRefreshKey((key) => key + 1);
    setDhcpPools([]);
    setRangeReservations([]);
  }, [subnet.id]);

  const startEditHeader = () => {
    setHeaderDraft({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "", updatedAt: subnet.updatedAt });
    setHeaderError(null);
    setEditingHeader(true);
  };

  const saveHeader = async () => {
    setHeaderError(null);
    setHeaderSaving(true);
    try {
      const vlan = headerDraft.vlan === "" ? null : Number(headerDraft.vlan);
      const updated = await updateSubnet(subnet.id, headerDraft.cidr.trim(), vlan, headerDraft.description.trim() || null, headerDraft.updatedAt);
      onDetailUpdated(updated);
      setEditingHeader(false);
    } catch (error) {
      setHeaderError(error.message);
    } finally {
      setHeaderSaving(false);
    }
  };

  const reloadHeader = async () => {
    setHeaderSaving(true);
    try {
      const current = await getSubnet(subnet.id);
      onDetailUpdated(current);
      setHeaderDraft({ cidr: current.cidr, vlan: current.vlan ?? "", description: current.description || "", updatedAt: current.updatedAt });
      setHeaderError(null);
    } catch (error) { setHeaderError(error.message); }
    finally { setHeaderSaving(false); }
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
  const heatmapSubnet = useMemo(() => ({ ...subnet, dhcpPools, rangeReservations }), [subnet, dhcpPools, rangeReservations]);
  const popoverAddress = selectedRecord || heatmapAddresses.find((item) => item.address === popoverIp) || null;

  const handleAddressesLoaded = useCallback((addresses, error) => {
    setHeatmapAddresses(addresses);
    setHeatmapError(error ? error.message : null);
  }, []);

  useUnsavedChanges(editingHeader && (headerDraft.cidr !== subnet.cidr || String(headerDraft.vlan) !== String(subnet.vlan ?? "") || headerDraft.description !== (subnet.description || "")), headerSaving);

  const handleAddressMutation = (updated) => {
    const selection = ++addressSelectionEpoch.current;
    if (popoverIp) getSubnetAddresses(subnet.id, { addressStart: popoverIp, addressEnd: popoverIp, limit: 1 }).then((page) => {
      if (addressSelectionEpoch.current === selection) setSelectedRecord(page.addresses[0] || null);
    }).catch(() => {});
    setAddressRefreshKey((key) => key + 1);
    onDetailUpdated(updated);
  };

  const allocateNext = async (metadata) => {
    const result = await allocateNextAddress(subnet.id, metadata);
    setAllocatingNext(false);
    setFocusedAddress({ address: result.address });
    handleAddressMutation(result.subnet);
  };

  const closePopover = useCallback((expectedIp) => {
    if (!shouldCloseAddressPopover(expectedIp, popoverIp)) return;
    addressSelectionEpoch.current += 1;
    const origin = popoverOriginRef.current;
    setPopoverIp(null);
    requestAnimationFrame(() => origin?.focus());
  }, [popoverIp]);

  const openAddress = useCallback((record, origin) => {
    if (!canLeaveWorkspace()) return;
    addressSelectionEpoch.current += 1;
    popoverOriginRef.current = origin || document.activeElement;
    setSelectedRecord(record);
    setPopoverIp(record.address);
    onAddressSelected?.(record.id);
  }, [onAddressSelected]);

  const handleHeatmapCellClick = useCallback((ip, cellElement) => {
    if (!canLeaveWorkspace()) return;
    addressSelectionEpoch.current += 1;
    popoverOriginRef.current = cellElement;
    const record = heatmapAddresses.find((item) => item.address === ip) || null;
    setSelectedRecord(record);
    setPopoverIp(ip);
    if (record) onAddressSelected?.(record.id);
  }, [heatmapAddresses, onAddressSelected]);

  useEffect(() => {
    closePopover();
  }, [subnet.id]);

  useEffect(() => {
    if (inventoryView !== "heatmap") return undefined;
    const targetAddress = heatmapAddresses.find((address) => focusedAddress ? address.address === focusedAddress.address : address.id === highlightedAddressId);
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
  }, [focusedAddress, inventoryView, handleHeatmapCellClick, heatmapAddresses, heatmapPage, highlightedAddressId, onAddressSelected, subnet.id]);

  useEffect(() => {
    if (!focusedAddress || inventoryView !== "table") return;
    let current = true;
    getSubnetAddresses(subnet.id, { addressStart: focusedAddress.address, addressEnd: focusedAddress.address, limit: 1 }).then((page) => {
      if (current && page.addresses[0]) { openAddress(page.addresses[0]); setFocusedAddress(null); }
    }).catch(() => {});
    return () => { current = false; };
  }, [focusedAddress, inventoryView, subnet.id, openAddress]);

  return (
    <div className={`ip-subnet-workspace ${popoverIp ? "ip-has-inspector" : ""}`}>
    <div className="ip-subnet-content">
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
      <header className="ip-object-heading">
        <div><h3 className="ip-object-cidr">{subnet.cidr}</h3><p className="tool-hint">{formatVlan(subnet.vlan)} · {subnet.description || "No description"}
          {lastScan && ` · last scanned ${formatTimestamp(lastScan.finishedAt)}`}</p></div>
        <div className="ip-object-actions">
          {canWrite && <button className="tool-btn tool-btn-primary" onClick={() => setAllocatingNext(true)}>Allocate next IP</button>}
          {canScan && <button className="tool-btn tool-btn-ghost" onClick={() => setConfirmingScan(true)}>Autodiscover</button>}
          {canScan && <ScanStatusIcon subnetId={subnet.id} />}
          <details className="ip-object-more" onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
            <summary className="tool-btn tool-btn-ghost">More</summary>
            <div className="ip-more-content">
              {canWrite && <button className="tool-btn tool-btn-ghost" onClick={(event) => { event.currentTarget.closest("details").open = false; startEditHeader(); }}>Edit subnet</button>}
              <button className="tool-btn tool-btn-ghost" onClick={downloadCsv} disabled={exporting || subnet.recordedCount === 0}>{exporting ? "Exporting…" : "Export CSV"}</button>
              {canWrite && <MoveSubnetForm key={subnet.id} subnet={subnet} onMoved={onMoved} disabled={deleting || scanning || headerSaving} />}
              {canWrite && <button className="tool-btn tool-btn-ghost ip-row-btn-danger" onClick={(event) => { event.currentTarget.closest("details").open = false; setConfirmingDelete(true); }} disabled={deleting}>Archive subnet</button>}
            </div>
          </details>
        </div>
      </header>
      {editingHeader && <div className="ip-header-edit">
        <label>CIDR<input className="tool-input" aria-label="Subnet CIDR" value={headerDraft.cidr} onChange={(event) => setHeaderDraft({ ...headerDraft, cidr: event.target.value })} /></label>
        <label>VLAN<input className="tool-input" aria-label="Subnet VLAN" value={headerDraft.vlan} onChange={(event) => setHeaderDraft({ ...headerDraft, vlan: event.target.value })} /></label>
        <label>Description<input className="tool-input" value={headerDraft.description} onChange={(event) => setHeaderDraft({ ...headerDraft, description: event.target.value })} /></label>
        <button className="tool-btn tool-btn-primary" onClick={saveHeader} disabled={headerSaving}>{headerSaving ? "Saving…" : "Save subnet"}</button>
        <button className="tool-btn tool-btn-ghost" onClick={() => setEditingHeader(false)} disabled={headerSaving}>Cancel</button>
      </div>}
      {confirmingDelete && <div className="ip-review-operation" role="region" aria-label="Archive subnet review">
        <p>Archive {subnet.cidr}? Review the subnet and its recorded addresses before confirming.</p>
        <label>Archive reason<input className="tool-input" value={archiveReason} onChange={(event) => setArchiveReason(event.target.value)} /></label>
        <button className="tool-btn tool-btn-ghost ip-row-btn-danger" onClick={() => onDelete(archiveReason)} disabled={deleting || !archiveReason.trim()}>{deleting ? "Archiving…" : "Confirm archive"}</button>
        <button className="tool-btn tool-btn-ghost" onClick={() => setConfirmingDelete(false)} disabled={deleting}>Cancel</button>
      </div>}
      {confirmingScan && <div className="ip-review-operation" role="region" aria-label="Subnet scan review">
        <p>Ping every address in {subnet.cidr}? This may take a while.</p>
        <button className="tool-btn tool-btn-primary" onClick={runAutodiscover} disabled={scanning}>{scanning ? scanProgress?.total > 0 ? `Scanning ${scanProgress.completed}/${scanProgress.total}…` : "Starting…" : "Confirm scan"}</button>
        <button className="tool-btn tool-btn-ghost" onClick={() => setConfirmingScan(false)} disabled={scanning}>Cancel</button>
      </div>}
      {allocatingNext && <AllocateNextAddressForm subnet={subnet} onAllocate={allocateNext} onCancel={() => setAllocatingNext(false)} />}
      {headerError && <div className="tool-error">{headerError}{headerError.includes("modified by another user") && <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={reloadHeader} disabled={headerSaving}>Reload current values</button>}</div>}
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

      <ViewTabs label="Subnet detail sections" value={detailSection} onChange={(section) => { if (canLeaveWorkspace()) { closePopover(); setDetailSection(section); } }}
        items={[{ id: "inventory", label: "Addresses" }, { id: "ranges", label: "DHCP & ranges" }, { id: "children", label: "Child subnets" }, { id: "history", label: "History" }, { id: "settings", label: "Settings" }]} />
      {detailSection === "history" && <AuditTimeline key={subnet.id} subnetId={subnet.id} title={`${subnet.cidr} history`} description="Changes recorded for this subnet and its addresses." showTarget />}
      {detailSection === "inventory" && <>
      <UtilizationBar subnet={subnet} />
      <div className="tool-summary">
        <div className="tool-stat"><div className="n">{subnet.totalAddresses.toLocaleString()}</div><div className="l">Total addresses</div></div>
        <div className="tool-stat"><div className="n">{subnet.usedCount}</div><div className="l">Used</div></div>
        <div className="tool-stat"><div className="n">{subnet.reservedCount}</div><div className="l">Reserved</div></div>
        <div className="tool-stat"><div className="n">{subnet.freeCount}</div><div className="l">Free (recorded)</div></div>
        <div className="tool-stat"><div className="n">{unallocated.toLocaleString()}</div><div className="l">Not recorded</div></div>
      </div>

      <div className="ip-inventory-view-toggle" role="group" aria-label="Address inventory view">
        <button type="button" className={`tool-btn ip-row-btn ${inventoryView === "heatmap" ? "tool-btn-primary" : "tool-btn-ghost"}`} onClick={() => setInventoryView("heatmap")} aria-pressed={inventoryView === "heatmap"}>Heatmap</button>
        <button type="button" className={`tool-btn ip-row-btn ${inventoryView === "table" ? "tool-btn-primary" : "tool-btn-ghost"}`} onClick={() => setInventoryView("table")} aria-pressed={inventoryView === "table"}>Table</button>
      </div>
      {inventoryView === "heatmap" ? (
        <div className="ip-heatmap-stage" ref={heatmapStageRef}>
          <SubnetHeatmap subnet={heatmapSubnet} subnets={subnets} onCellClick={handleHeatmapCellClick} page={heatmapPage} onPageChange={setHeatmapPage} focusedAddress={focusedAddress} addresses={heatmapAddresses} onAddressesLoaded={handleAddressesLoaded} refreshKey={addressRefreshKey} />
          {heatmapError && <div className="tool-error" role="alert">Heatmap failed to load: {heatmapError}</div>}
        </div>
      ) : (
        <AddressTable canWrite={canWrite} subnetId={subnet.id} refreshKey={addressRefreshKey} highlightedAddressId={highlightedAddressId} tags={tags} subnets={subnets} onMutated={handleAddressMutation} onAddressOpen={openAddress} />
      )}
      </>}
      {detailSection === "ranges" && <>
      <h3 className="ip-section-sub-title">DHCP Pools</h3>
      <DhcpPoolManager canWrite={canWrite} subnetId={subnet.id} subnets={subnets} onPoolsChanged={setDhcpPools} />
      <h3 className="ip-section-sub-title">Range reservations</h3>
      <RangeReservationManager canWrite={canWrite} subnetId={subnet.id} onReservationsChanged={(reservations) => { setRangeReservations(reservations); setAddressRefreshKey((key) => key + 1); }} />
      </>}
      {detailSection === "children" && (
        <>
          <h3 className="ip-section-sub-title">Nested subnets <span className="tool-hint">{children.length}</span></h3>
          <div className="tool-table-wrap ip-table-wrap-full">
            <table className="tool-table">
              <thead><tr><th>CIDR</th><th>VLAN</th><th>Description</th><th>Recorded</th></tr></thead>
              <tbody>{children.map((child) => (
                <tr key={child.id} className="ip-child-row">
                  <td className="ip-mono"><button className="ip-subnet-link" onClick={() => onSelectSubnet(child.id)}>{child.cidr}</button></td><td>{formatVlan(child.vlan)}</td><td>{child.description || "—"}</td>
                  <td>{child.usedCount}u · {child.reservedCount}r · {child.freeCount}f</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}

      {detailSection === "children" && children.length === 0 && <div className="tool-empty">No child subnets in this network.</div>}
      {detailSection === "settings" && <>
      <h3 className="ip-section-sub-title">Tags</h3>
      <TagSelector disabled={!canWrite} canCreate={permissions.admin} value={subnetTagIds.map((tag) => tag.id)} onChange={onTagChange} allTags={tags} placeholder="Add tags to this subnet" onTagCreated={onTagCreated} />
      {permissions.admin && <ScanExcludeManager subnetId={subnet.id} />}
      </>}
    </div>
    {popoverIp && <AddressPopover inspector ip={popoverIp} address={popoverAddress} subnetId={subnet.id} onClose={closePopover} onUpdated={handleAddressMutation} tags={tags} addressTags={popoverAddress ? addressTagIds[popoverAddress.id] || [] : []} onAddressTagChange={onAddressTagChange} onTagCreated={onTagCreated} canWrite={canWrite} canScan={canScan} canAdmin={permissions.admin} />}
    </div>
  );
}
