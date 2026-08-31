import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

const MAX_HEATMAP_ADDRESSES = 65536;
const CELL_MIN_PX = 14;
const CELL_GAP_PX = 3;
const COVERAGE_FREE = 0;
const COVERAGE_CHILD = 1;
const COVERAGE_DHCP = 2;
const ROWS_PER_PAGE = 20;

const STATUS_LABELS = {
  available: "Available",
  used: "Used",
  free: "Free",
  reserved: "Reserved",
};

function ipv4ToNumber(ip) {
  return ip
    .split(".")
    .map(Number)
    .reduce((value, octet) => value * 256 + octet, 0);
}

function numberToIpv4(value) {
  return [
    Math.floor(value / 16777216) % 256,
    Math.floor(value / 65536) % 256,
    Math.floor(value / 256) % 256,
    value % 256,
  ].join(".");
}

function rangeToSegments(startOffset, endOffset, columns) {
  const segments = [];
  let current = startOffset;

  while (current <= endOffset) {
    const row = Math.floor(current / columns);
    const rowEnd = Math.min(endOffset, (row + 1) * columns - 1);
    segments.push({
      gridRowStart: row + 1,
      gridRowEnd: row + 2,
      gridColumnStart: (current % columns) + 1,
      gridColumnEnd: (rowEnd % columns) + 2,
    });
    current = rowEnd + 1;
  }

  return segments;
}

export default function SubnetHeatmap({
  subnet,
  subnets = [],
  onCellClick,
  page,
  onPageChange,
  focusedAddressId,
}) {
  const containerRef = useRef(null);
  const hoveredIndexRef = useRef(null);
  const [columns, setColumns] = useState(32);
  const [activeIndex, setActiveIndex] = useState(0);
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [tooltipPosition, setTooltipPosition] = useState(null);
  const totalAddresses = Number(subnet.totalAddresses || 0);
  const heatmapSupported = totalAddresses > 0 && totalAddresses <= MAX_HEATMAP_ADDRESSES;
  const addressesPerPage = columns * ROWS_PER_PAGE;
  const pageCount = Math.max(1, Math.ceil(totalAddresses / addressesPerPage));
  const currentPage = Math.min(page, pageCount - 1);
  const pageStart = currentPage * addressesPerPage;
  const pageEnd = Math.min(totalAddresses, pageStart + addressesPerPage);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;

    const measure = () => {
      const width = element.clientWidth;
      if (!width) return;
      const nextColumns = Math.max(
        1,
        Math.floor((width + CELL_GAP_PX) / (CELL_MIN_PX + CELL_GAP_PX))
      );
      setColumns(nextColumns);
      element.style.setProperty("--ip-heatmap-cols", nextColumns);
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [heatmapSupported]);

  const prepared = useMemo(() => {
    if (totalAddresses <= 0 || totalAddresses > MAX_HEATMAP_ADDRESSES) {
      return { cells: [], childRanges: [], poolRanges: [] };
    }

    const subnetStart = ipv4ToNumber(subnet.cidr.split("/")[0]);
    const subnetPrefix = Number(subnet.cidr.split("/")[1]);
    const existingAddresses = new Map(
      (subnet.addresses || []).map((address) => [address.address, address])
    );
    const coverage = new Uint8Array(totalAddresses);
    const childRanges = [];
    const poolRanges = [];

    for (const child of subnets) {
      if (child.parentId !== subnet.id) continue;
      const childPrefix = Number(child.cidr.split("/")[1]);
      if (childPrefix <= subnetPrefix) continue;

      const rawStart = ipv4ToNumber(child.cidr.split("/")[0]) - subnetStart;
      const rawEnd = rawStart + 2 ** (32 - childPrefix) - 1;
      if (rawEnd < 0 || rawStart >= totalAddresses) continue;

      const startOffset = Math.max(0, rawStart);
      const endOffset = Math.min(totalAddresses - 1, rawEnd);
      childRanges.push({ ...child, startOffset, endOffset });
      coverage.fill(COVERAGE_CHILD, startOffset, endOffset + 1);
    }

    for (const pool of subnet.dhcpPools || []) {
      const rawStart = ipv4ToNumber(pool.start_ip) - subnetStart;
      const rawEnd = ipv4ToNumber(pool.end_ip) - subnetStart;
      if (rawEnd < 0 || rawStart >= totalAddresses) continue;

      const startOffset = Math.max(0, rawStart);
      const endOffset = Math.min(totalAddresses - 1, rawEnd);
      poolRanges.push({ ...pool, startOffset, endOffset });
      for (let offset = startOffset; offset <= endOffset; offset += 1) {
        if (coverage[offset] === COVERAGE_FREE) coverage[offset] = COVERAGE_DHCP;
      }
    }

    const cells = new Array(totalAddresses);
    for (let offset = 0; offset < totalAddresses; offset += 1) {
      const ip = numberToIpv4(subnetStart + offset);
      const address = existingAddresses.get(ip) || null;
      const coverageType = coverage[offset];
      const status = address?.status || "available";
      cells[offset] = {
        ip,
        addressId: address?.id || null,
        status,
        hostname: address?.hostname || null,
        description: address?.description || null,
        isPlaceholder: coverageType !== COVERAGE_FREE,
      };
    }

    return { cells, childRanges, poolRanges };
  }, [subnet, subnets, totalAddresses]);

  useEffect(() => {
    if (page !== currentPage) onPageChange(currentPage);
  }, [currentPage, onPageChange, page]);

  useEffect(() => {
    if (!focusedAddressId) return;
    const addressOffset = prepared.cells.findIndex(
      (cell) => cell.addressId === focusedAddressId
    );
    if (addressOffset >= 0) onPageChange(Math.floor(addressOffset / addressesPerPage));
  }, [addressesPerPage, focusedAddressId, onPageChange, prepared.cells]);

  useEffect(() => {
    hoveredIndexRef.current = null;
    setHoveredIndex(null);
    setTooltipPosition(null);
  }, [columns, currentPage, prepared.cells, subnet.id]);

  useEffect(() => {
    const firstFocusable = prepared.cells.findIndex(
      (cell, index) => index >= pageStart && index < pageEnd && !cell.isPlaceholder
    );
    if (activeIndex < pageStart || activeIndex >= pageEnd || prepared.cells[activeIndex]?.isPlaceholder) {
      setActiveIndex(firstFocusable >= 0 ? firstFocusable : pageStart);
    }
  }, [activeIndex, pageEnd, pageStart, prepared.cells]);

  const cellElements = useMemo(
    () =>
      prepared.cells.slice(pageStart, pageEnd).map((cell, pageIndex) => {
        const index = pageStart + pageIndex;
        return (
        cell.isPlaceholder ? (
          <div
            key={cell.ip}
            className="ip-heatmap-cell ip-heatmap-placeholder"
            aria-hidden="true"
          />
        ) : (
          <button
            key={cell.ip}
            type="button"
            className={`ip-heatmap-cell ip-heatmap-${cell.status === "available" ? "free" : cell.status}`}
            data-cell-index={index}
            data-ip={cell.ip}
            data-address-id={cell.addressId || ""}
            aria-label={`${cell.ip}: ${STATUS_LABELS[cell.status] || cell.status}`}
            tabIndex={index === activeIndex ? 0 : -1}
          />
        )
        );
      }),
    [activeIndex, pageEnd, pageStart, prepared.cells]
  );

  const overlayElements = useMemo(() => {
    const visibleSegments = (range) => {
      const startOffset = Math.max(range.startOffset, pageStart);
      const endOffset = Math.min(range.endOffset, pageEnd - 1);
      if (startOffset > endOffset) return [];
      return rangeToSegments(startOffset - pageStart, endOffset - pageStart, columns);
    };

    const children = prepared.childRanges.flatMap((child) =>
      visibleSegments(child).map((style, index) => (
        <div
          key={`child-${child.id}-${index}`}
          className="ip-heatmap-child-outline"
          style={style}
        >
          {index === 0 && child.startOffset >= pageStart && child.startOffset < pageEnd && (
            <div
              className="ip-heatmap-child-label"
              title={`${child.cidr} ${child.vlan ? `(VLAN ${child.vlan})` : ""} ${child.description ? `- ${child.description}` : ""}`}
            >
              {child.cidr}
            </div>
          )}
        </div>
      ))
    );

    const pools = prepared.poolRanges.flatMap((pool) =>
      visibleSegments(pool).map((style, index) => (
        <div
          key={`pool-${pool.id}-${index}`}
          className="ip-heatmap-dhcp-block"
          style={style}
        >
          {index === 0 && pool.startOffset >= pageStart && pool.startOffset < pageEnd && (
            <div
              className="ip-heatmap-dhcp-label"
              title={`${pool.name || "DHCP Pool"}: ${pool.start_ip} - ${pool.end_ip} ${pool.description ? `- ${pool.description}` : ""}`}
            >
              {pool.name || "DHCP"}
            </div>
          )}
        </div>
      ))
    );

    return [...children, ...pools];
  }, [columns, pageEnd, pageStart, prepared.childRanges, prepared.poolRanges]);

  const getCellTarget = useCallback((event) => {
    const cellElement = event.target.closest(".ip-heatmap-cell[data-cell-index]");
    if (!cellElement || !event.currentTarget.contains(cellElement)) return null;
    const index = Number(cellElement.dataset.cellIndex);
    const cell = prepared.cells[index];
    return cell && !cell.isPlaceholder ? { cell, cellElement, index } : null;
  }, [prepared.cells]);

  const handleMouseMove = useCallback((event) => {
    const target = getCellTarget(event);
    if (!target) {
      if (hoveredIndexRef.current !== null) {
        hoveredIndexRef.current = null;
        setHoveredIndex(null);
        setTooltipPosition(null);
      }
      return;
    }
    if (hoveredIndexRef.current === target.index) return;

    hoveredIndexRef.current = target.index;
    const cellRect = target.cellElement.getBoundingClientRect();
    const containerRect = event.currentTarget.getBoundingClientRect();
    setHoveredIndex(target.index);
    setTooltipPosition({
      left: cellRect.left - containerRect.left + cellRect.width / 2,
      top: cellRect.top - containerRect.top,
    });
  }, [getCellTarget]);

  const handleMouseLeave = useCallback(() => {
    hoveredIndexRef.current = null;
    setHoveredIndex(null);
    setTooltipPosition(null);
  }, []);

  const handleClick = useCallback((event) => {
    const target = getCellTarget(event);
    if (target) {
      setActiveIndex(target.index);
      onCellClick?.(target.cell.ip, target.cellElement);
    }
  }, [getCellTarget, onCellClick]);

  const handleKeyDown = useCallback((event) => {
    const target = getCellTarget(event);
    if (!target) return;
    const deltas = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    let nextIndex = target.index + delta;
    while (
      nextIndex >= pageStart &&
      nextIndex < pageEnd &&
      prepared.cells[nextIndex]?.isPlaceholder
    ) {
      nextIndex += delta;
    }
    if (nextIndex < pageStart || nextIndex >= pageEnd || !prepared.cells[nextIndex]) return;
    setActiveIndex(nextIndex);
    containerRef.current
      ?.querySelector(`[data-cell-index="${nextIndex}"]`)
      ?.focus();
  }, [columns, getCellTarget, pageEnd, pageStart, prepared.cells]);

  if (totalAddresses > MAX_HEATMAP_ADDRESSES) {
    return (
      <div className="tool-warning">
        Heatmap is available for subnets up to /16 (65,536 addresses). Consider splitting this subnet into smaller nested subnets.
      </div>
    );
  }

  const tooltipCell = hoveredIndex === null ? null : prepared.cells[hoveredIndex];

  return (
    <>
      <div
        className="ip-heatmap-container"
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        role="grid"
        aria-label={`Address heatmap for ${subnet.cidr}`}
      >
        {cellElements}
        {overlayElements}
        {tooltipCell && tooltipPosition && (
          <div
            className="ip-heatmap-tooltip"
            style={{ left: tooltipPosition.left, top: tooltipPosition.top }}
          >
            <div className="ip-heatmap-tooltip-ip">{tooltipCell.ip}</div>
            <div className="ip-heatmap-tooltip-status">
              {STATUS_LABELS[tooltipCell.status] || tooltipCell.status}
            </div>
            {tooltipCell.hostname && (
              <div className="ip-heatmap-tooltip-hostname">{tooltipCell.hostname}</div>
            )}
            {tooltipCell.description && (
              <div className="ip-heatmap-tooltip-description">{tooltipCell.description}</div>
            )}
          </div>
        )}
      </div>
      {pageCount > 1 && (
        <div className="ip-heatmap-pagination">
          <span className="ip-heatmap-page-range">
            {prepared.cells[pageStart]?.ip} - {prepared.cells[pageEnd - 1]?.ip}
          </span>
          <div className="ip-heatmap-page-actions">
            <button
              type="button"
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage === 0}
            >
              Previous
            </button>
            <span className="ip-heatmap-page-count">
              Page {currentPage + 1} of {pageCount}
            </span>
            <button
              type="button"
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage === pageCount - 1}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </>
  );
}
