import React, { useEffect, useMemo, useRef, useState } from "react";
import { getSubnetAddresses } from "./api.js";
import { formatTimestamp } from "./logic.js";

const PAGE_SIZES = [25, 50, 100];
const STATUS_LABELS = {
  used: "Used",
  free: "Free",
  reserved: "Reserved",
};

function SortButton({ column, activeColumn, direction, onSort, children }) {
  const active = activeColumn === column;
  return (
    <button
      type="button"
      className={`ip-address-sort ${active ? "active" : ""}`}
      onClick={() => onSort(column)}
      aria-label={`Sort by ${children}${active ? `, currently ${direction === "asc" ? "ascending" : "descending"}` : ""}`}
    >
      <span>{children}</span>
      <span aria-hidden="true">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
    </button>
  );
}

export default function AddressTable({ subnetId, refreshKey = 0, highlightedAddressId, onAddressOpen }) {
  const [addresses, setAddresses] = useState([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("address");
  const [direction, setDirection] = useState("asc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const requestRef = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setOffset(0);
      setQuery(queryInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setLoading(true);
    setError(null);
    getSubnetAddresses(subnetId, { limit, offset, status, query, sort, direction })
      .then((page) => {
        if (requestRef.current !== requestId) return;
        if (page.total > 0 && offset >= page.total) {
          setOffset(Math.max(0, Math.floor((page.total - 1) / limit) * limit));
          return;
        }
        setAddresses(page.addresses);
        setTotal(page.total);
      })
      .catch((err) => {
        if (requestRef.current === requestId) setError(err.message);
      })
      .finally(() => {
        if (requestRef.current === requestId) setLoading(false);
      });
  }, [direction, limit, offset, query, refreshKey, sort, status, subnetId]);

  useEffect(() => {
    setOffset(0);
    setQueryInput("");
    setQuery("");
    setStatus("");
    setSort("address");
    setDirection("asc");
  }, [subnetId]);

  const pageNumber = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + addresses.length, total);
  const hasFilters = Boolean(status || query);
  const resultLabel = useMemo(() => {
    if (loading) return "Loading address records";
    if (total === 0) return hasFilters ? "No addresses match these filters" : "No recorded addresses";
    return `Showing ${rangeStart}–${rangeEnd} of ${total} recorded addresses`;
  }, [hasFilters, loading, rangeEnd, rangeStart, total]);

  const handleSort = (column) => {
    setOffset(0);
    if (sort === column) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSort(column);
      setDirection("asc");
    }
  };

  const clearFilters = () => {
    setQueryInput("");
    setQuery("");
    setStatus("");
    setOffset(0);
  };

  return (
    <section className="ip-address-table-section" aria-labelledby="ip-address-table-title">
      <div className="ip-address-table-heading">
        <div>
          <h3 id="ip-address-table-title" className="ip-section-sub-title">Address records</h3>
          <p className="tool-hint">Search and inspect recorded hosts without loading the whole subnet.</p>
        </div>
        <span className="ip-address-count" aria-live="polite">{resultLabel}</span>
      </div>

      <div className="ip-address-filters">
        <label className="ip-address-search-field">
          <span>Search records</span>
          <input
            className="tool-input"
            type="search"
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder="IP, hostname, or description"
          />
        </label>
        <label>
          <span>Status</span>
          <select
            className="tool-input"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            <option value="used">Used</option>
            <option value="free">Free</option>
            <option value="reserved">Reserved</option>
          </select>
        </label>
        <label>
          <span>Rows</span>
          <select
            className="tool-input"
            value={limit}
            onChange={(event) => {
              setLimit(Number(event.target.value));
              setOffset(0);
            }}
          >
            {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
        {hasFilters && (
          <button type="button" className="tool-btn tool-btn-ghost" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </div>

      {error && <div className="tool-error" role="alert">{error}</div>}
      {!error && (
        <div className="tool-table-wrap ip-address-table-wrap" aria-busy={loading}>
          <table className="tool-table ip-address-table">
            <caption className="sr-only">Recorded addresses for the selected subnet</caption>
            <thead>
              <tr>
                <th aria-sort={sort === "address" ? (direction === "asc" ? "ascending" : "descending") : "none"}>
                  <SortButton column="address" activeColumn={sort} direction={direction} onSort={handleSort}>Address</SortButton>
                </th>
                <th aria-sort={sort === "status" ? (direction === "asc" ? "ascending" : "descending") : "none"}>
                  <SortButton column="status" activeColumn={sort} direction={direction} onSort={handleSort}>Status</SortButton>
                </th>
                <th aria-sort={sort === "hostname" ? (direction === "asc" ? "ascending" : "descending") : "none"}>
                  <SortButton column="hostname" activeColumn={sort} direction={direction} onSort={handleSort}>Hostname</SortButton>
                </th>
                <th>Team</th>
                <th>Environment</th>
                <th aria-sort={sort === "updatedAt" ? (direction === "asc" ? "ascending" : "descending") : "none"}>
                  <SortButton column="updatedAt" activeColumn={sort} direction={direction} onSort={handleSort}>Updated</SortButton>
                </th>
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="7" className="ip-address-table-state">Loading records…</td></tr>
              ) : addresses.length === 0 ? (
                <tr><td colSpan="7" className="ip-address-table-state">{resultLabel}</td></tr>
              ) : addresses.map((address) => (
                <tr key={address.id} className={address.id === highlightedAddressId ? "ip-row-highlighted" : ""}>
                  <td data-label="Address" className="ip-subnet-cidr">{address.address}</td>
                  <td data-label="Status"><span className={`tool-pill tool-pill-${address.status === "used" ? "ok" : address.status === "reserved" ? "warn" : "muted"}`}>{STATUS_LABELS[address.status]}</span></td>
                  <td data-label="Hostname">{address.hostname || "—"}</td>
                  <td data-label="Team">{address.team || "—"}</td>
                  <td data-label="Environment">{address.environment || "—"}</td>
                  <td data-label="Updated">{formatTimestamp(address.updatedAt)}</td>
                  <td data-label="Actions" className="ip-actions-cell">
                    <button type="button" className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => onAddressOpen(address)}>
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="ip-address-pagination" aria-label="Address table pagination">
        <span>Page {pageNumber} of {pageCount}</span>
        <div>
          <button type="button" className="tool-btn tool-btn-ghost" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0 || loading}>Previous</button>
          <button type="button" className="tool-btn tool-btn-ghost" onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total || loading}>Next</button>
        </div>
      </div>
    </section>
  );
}
