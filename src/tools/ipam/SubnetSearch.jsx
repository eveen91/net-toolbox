import React, { useEffect, useMemo, useRef, useState } from "react";
import { formatVlan } from "./logic.js";
import { searchAddresses } from "./api.js";
import TagBadge from "./TagBadge.jsx";
import TagSelector from "./TagSelector.jsx";

/**
 * Global Search box for finding subnets (by CIDR / description / VLAN)
 * and searching hostnames (or IP addresses / partial matches) across all tracked subnets.
 */
export default function SubnetSearch({ subnets, selectedId, onSelect, autoFocus, tags = [], selectedTagIds = [], onTagFilterChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const [addressMatches, setAddressMatches] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  const containerRef = useRef(null);
  const inputRef = useRef(null);

  const subnetMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    let filtered = subnets;

    if (selectedTagIds.length > 0) {
      // Filter subnets that have ALL selected tags
      filtered = filtered.filter((s) => {
        const tagIds = s.tagIds || [];
        return selectedTagIds.every((tid) => tagIds.includes(tid));
      });
    }

    if (!q) return filtered;
    return filtered.filter(
      (s) =>
        s.cidr.toLowerCase().includes(q) ||
        (s.description && s.description.toLowerCase().includes(q)) ||
        (s.vlan != null && String(s.vlan).includes(q))
    );
  }, [subnets, query, selectedTagIds]);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setAddressMatches([]);
      setIsSearching(false);
      return;
    }

    setAddressMatches([]);
    setIsSearching(true);
    let cancelled = false;

    const timer = setTimeout(async () => {
      try {
        const results = await searchAddresses(q);
        if (!cancelled) {
          setAddressMatches(results);
        }
      } catch {
        if (!cancelled) {
          setAddressMatches([]);
        }
      } finally {
        if (!cancelled) {
          setIsSearching(false);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  const allMatches = useMemo(() => {
    const list = [];
    subnetMatches.forEach((s) => list.push({ type: "subnet", data: s, key: `s-${s.id}` }));
    if (query.trim()) {
      addressMatches.forEach((a) => list.push({ type: "address", data: a, key: `a-${a.id}` }));
    }
    return list;
  }, [subnetMatches, addressMatches, query]);

  useEffect(() => {
    setHighlightIndex((i) => (allMatches.length === 0 ? 0 : Math.min(i, allMatches.length - 1)));
  }, [allMatches.length]);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const selectedSubnet = subnets.find((s) => s.id === selectedId);

  const chooseSubnet = (subnet) => {
    onSelect(subnet.id);
    setQuery("");
    setOpen(false);
  };

  const chooseAddress = (addr) => {
    onSelect(addr.subnetId, addr.id);
    setQuery("");
    setOpen(false);
  };

  const handleKeyDown = (e) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (!open) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, allMatches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = allMatches[highlightIndex];
      if (chosen) {
        if (chosen.type === "subnet") chooseSubnet(chosen.data);
        else if (chosen.type === "address") chooseAddress(chosen.data);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  const handleTagFilterChange = (newIds) => {
    onTagFilterChange(newIds);
  };

  return (
    <div className="ip-search" ref={containerRef}>
      <div className="ip-search-field">
        <input
          ref={inputRef}
          autoFocus={autoFocus}
          className="tool-input ip-search-input"
          placeholder={
            selectedSubnet
              ? `${selectedSubnet.cidr} — search subnets or hostnames`
              : subnets.length === 0
              ? "No subnets yet — add one to get started"
              : "Search subnets, hostnames, or IP addresses…"
          }
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHighlightIndex(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
        />
        {query && (
          <button
            type="button"
            className="ip-search-clear"
            onClick={() => {
              setQuery("");
              setOpen(false);
              inputRef.current?.focus();
            }}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>

      {selectedTagIds.length > 0 && (
        <div className="ip-tag-filter-bar">
          <span className="ip-tag-filter-bar-label">Filter by tags:</span>
          {tags
            .filter((t) => selectedTagIds.includes(t.id))
            .map((tag) => (
              <TagBadge
                key={tag.id}
                tag={tag}
                size="sm"
                removable
                onRemove={() => handleTagFilterChange(selectedTagIds.filter((id) => id !== tag.id))}
              />
            ))}
          <button
            type="button"
            className="tool-btn tool-btn-ghost ip-tag-filter-bar-clear"
            onClick={() => handleTagFilterChange([])}
          >
            Clear all
          </button>
        </div>
      )}

      <div className="ip-tag-filter-bar" style={{ borderBottom: "none", marginBottom: 0 }}>
        <span className="ip-tag-filter-bar-label">Add tag filter:</span>
        <TagSelector
          value={selectedTagIds}
          onChange={handleTagFilterChange}
          allTags={tags}
          placeholder="Select tags to filter"
        />
      </div>

      {open && (
        <div className="ip-search-dropdown">
          {!query.trim() && subnetMatches.length === 0 && (
            <div className="ip-search-empty">
              {subnets.length === 0
                ? "No subnets yet — add one to get started."
                : "No subnets recorded."}
            </div>
          )}

          {query.trim() && isSearching && allMatches.length === 0 && (
            <div className="ip-search-empty">Searching…</div>
          )}

          {query.trim() && !isSearching && allMatches.length === 0 && (
            <div className="ip-search-empty">No matching subnets or hostnames found.</div>
          )}

          {subnetMatches.length > 0 && query.trim() && (
            <div className="ip-search-section-header">Subnets ({subnetMatches.length})</div>
          )}

          {subnetMatches.map((s) => {
            const itemIndex = allMatches.findIndex(
              (m) => m.type === "subnet" && m.data.id === s.id
            );
            return (
              <button
                type="button"
                key={`sub-${s.id}`}
                className={`ip-search-option ${
                  itemIndex === highlightIndex ? "highlighted" : ""
                } ${s.id === selectedId ? "current" : ""}`}
                onMouseEnter={() => setHighlightIndex(itemIndex)}
                onClick={() => chooseSubnet(s)}
              >
                <span className="ip-search-option-top">
                  <span className="ip-search-option-cidr">{s.cidr}</span>
                  {s.vlan != null && <span className="ip-subnet-vlan">{formatVlan(s.vlan)}</span>}
                </span>
                <span className="ip-search-option-bottom">
                  <span className="tool-hint">{s.description || "no description"}</span>
                  <span className="ip-subnet-counts">
                    {s.usedCount}u · {s.reservedCount}r · {s.freeCount}f
                  </span>
                </span>
              </button>
            );
          })}

          {addressMatches.length > 0 && query.trim() && (
            <div className="ip-search-section-header">
              Hostnames & Addresses ({addressMatches.length})
            </div>
          )}

          {addressMatches.map((a) => {
            const itemIndex = allMatches.findIndex(
              (m) => m.type === "address" && m.data.id === a.id
            );
            return (
              <button
                type="button"
                key={`addr-${a.id}`}
                className={`ip-search-option ${
                  itemIndex === highlightIndex ? "highlighted" : ""
                }`}
                onMouseEnter={() => setHighlightIndex(itemIndex)}
                onClick={() => chooseAddress(a)}
              >
                <span className="ip-search-option-top">
                  <span className="ip-search-option-hostname">
                    {a.hostname || a.address}
                  </span>
                  {a.hostname && <span className="ip-search-option-addr">{a.address}</span>}
                  <span className={`ip-scan-status-badge ${a.status}`}>{a.status}</span>
                </span>
                <span className="ip-search-option-bottom">
                  <span className="tool-hint">
                    Subnet: <span className="ip-mono">{a.subnetCidr}</span>
                    {a.subnetVlan != null ? ` (VLAN ${a.subnetVlan})` : ""}
                    {a.description ? ` · ${a.description}` : ""}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
