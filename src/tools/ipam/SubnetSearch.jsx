import React, { useEffect, useMemo, useRef, useState } from "react";
import { formatVlan } from "./logic.js";

/**
 * Search/jump control for finding a subnet by CIDR. Filters the flat
 * `subnets` list as the user types and lets them pick a match with the
 * mouse or the keyboard (Up/Down to move, Enter to select, Esc to close).
 *
 * Pure presentation + local filtering — selection is handed back to the
 * caller via onSelect(id), which already knows how to fetch subnet detail
 * (see Ipam.jsx's selectSubnet). This component holds no subnet-detail
 * state of its own.
 */
export default function SubnetSearch({ subnets, selectedId, onSelect, autoFocus }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return subnets;
    return subnets.filter((s) => s.cidr.toLowerCase().includes(q));
  }, [subnets, query]);

  // Keep the highlighted row in range whenever the match set changes size.
  useEffect(() => {
    setHighlightIndex((i) => (matches.length === 0 ? 0 : Math.min(i, matches.length - 1)));
  }, [matches.length]);

  // Close the dropdown on outside click.
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

  const choose = (subnet) => {
    onSelect(subnet.id);
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
      setHighlightIndex((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = matches[highlightIndex];
      if (chosen) choose(chosen);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
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
              ? `${selectedSubnet.cidr} — search to jump to another subnet`
              : subnets.length === 0
              ? "No subnets yet — add one to get started"
              : "Search subnets by CIDR…"
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

      {open && (
        <div className="ip-search-dropdown">
          {matches.length === 0 && (
            <div className="ip-search-empty">
              {subnets.length === 0 ? "No subnets yet — add one to get started." : "No subnets match that CIDR."}
            </div>
          )}
          {matches.map((s, i) => (
            <button
              type="button"
              key={s.id}
              className={`ip-search-option ${i === highlightIndex ? "highlighted" : ""} ${
                s.id === selectedId ? "current" : ""
              }`}
              onMouseEnter={() => setHighlightIndex(i)}
              onClick={() => choose(s)}
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
          ))}
        </div>
      )}
    </div>
  );
}