import React, { useEffect, useRef, useState } from "react";
import { searchTags, createTag } from "./api.js";
import TagBadge from "./TagBadge.jsx";

/**
 * Multi-select dropdown for choosing tags.
 *
 * Shows a search box that filters available tags, displays selected tags as
 * removable chips, and allows creating a new tag inline.
 *
 * Props:
 *   value      – array of selected tag ids
 *   onChange   – (ids) => void
 *   allTags    – optional pre-loaded tag list; if absent, loads on open
 *   placeholder – string (default "Search or create tag…")
 *   disabled   – prevents changes while a parent operation is pending
 *   onTagCreated – receives a newly created tag so parent caches stay current
 */
export default function TagSelector({ value = [], onChange, allTags: propAllTags, placeholder, disabled = false, onTagCreated }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [newTagMode, setNewTagMode] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [createError, setCreateError] = useState(null);
  const [newTagColor, setNewTagColor] = useState("#6366f1");

  const containerRef = useRef(null);
  const inputRef = useRef(null);

  const selectedIds = new Set(value);
  const all = propAllTags || [];

  // Debounced search — show all tags when query is empty, filtered results otherwise
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(all.filter((t) => !selectedIds.has(t.id)));
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    let cancelled = false;
    searchTags(q)
      .then((tags) => {
        if (!cancelled) setResults(tags.filter((t) => !selectedIds.has(t.id)));
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setIsSearching(false);
      });
    return () => { cancelled = true; };
  }, [query, selectedIds, all]);

  // Click-outside closes dropdown
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggleTag = async (tagId) => {
    if (disabled) return;
    const next = selectedIds.has(tagId)
      ? value.filter((id) => id !== tagId)
      : [...value, tagId];
    await onChange(next);
  };

  const removeTag = async (tagId) => {
    if (disabled) return;
    await onChange(value.filter((id) => id !== tagId));
  };

  const createAndAdd = async () => {
    if (disabled) return;
    const name = newTagName.trim();
    if (!name) return;
    try {
      const created = await createTag({ name, color: newTagColor });
      onTagCreated?.(created);
      await onChange([...value, created.id]);
      setNewTagMode(false);
      setNewTagName("");
      setNewTagColor("#6366f1");
      setCreateError(null);
      setOpen(false);
    } catch (e) {
      setCreateError(e.message);
    }
  };

  const displayResults =
    isSearching ? [] : results;

  return (
    <div className="ip-tag-selector" ref={containerRef}>
      <div className="ip-tag-selector-chips">
        {value.map((tagId) => {
          const tag = all.find((t) => t.id === tagId);
          if (!tag) return null;
          return (
            <TagBadge
              key={tagId}
              tag={tag}
              size="sm"
              removable={!disabled}
              onRemove={removeTag}
            />
          );
        })}

        {newTagMode ? (
          <div className="ip-tag-selector-new">
            <input
              className="tool-input ip-tag-selector-new-input"
              placeholder="Tag name"
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              disabled={disabled}
              onKeyDown={(e) => {
                if (e.key === "Enter") void createAndAdd();
                if (e.key === "Escape") { setNewTagMode(false); setNewTagName(""); }
              }}
              autoFocus
            />
            <input
              type="color"
              className="ip-tag-selector-color"
              value={newTagColor}
              onChange={(e) => setNewTagColor(e.target.value)}
              disabled={disabled}
            />
            <button type="button" className="tool-btn tool-btn-sm" onClick={createAndAdd} disabled={disabled}>
              Create
            </button>
            <button type="button" className="tool-btn tool-btn-ghost tool-btn-sm" onClick={() => { setNewTagMode(false); setNewTagName(""); }} disabled={disabled}>
              Cancel
            </button>
            {createError && <span className="tool-error ip-tag-selector-create-error">{createError}</span>}
          </div>
        ) : (
          <button
            type="button"
            className="tool-btn tool-btn-ghost ip-tag-selector-add-btn"
            onClick={() => setNewTagMode(true)}
            disabled={disabled}
          >
            + New tag
          </button>
        )}
      </div>

      <button
        type="button"
          className="ip-tag-selector-toggle"
          onClick={() => setOpen((o) => !o)}
          disabled={disabled}
      >
        {open ? "▾" : "▸"} {placeholder || "Tags"}
      </button>

      {open && (
        <div className="ip-tag-selector-dropdown">
          <input
            className="tool-input ip-tag-selector-search"
            placeholder="Search tags…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={disabled}
            autoFocus
          />

          {!query.trim() && !newTagMode && results.length > 0 && (
            <div className="ip-tag-selector-hint">
              Showing all tags ({results.length} available)
            </div>
          )}

          {isSearching && <div className="ip-tag-selector-empty">Searching…</div>}

          {!isSearching && displayResults.length === 0 && query.trim() && (
            <div className="ip-tag-selector-empty">No matching tags.</div>
          )}

          {displayResults.map((tag) => (
            <button
              key={tag.id}
              type="button"
              className="ip-tag-selector-option"
              onMouseDown={(e) => {
                e.preventDefault();
                void toggleTag(tag.id);
              }}
              disabled={disabled}
            >
              <span className="ip-tag-selector-option-dot" style={{ backgroundColor: tag.color }} />
              <span className="ip-tag-selector-option-name">{tag.name}</span>
              {tag.description && <span className="ip-tag-selector-option-desc">{tag.description}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
