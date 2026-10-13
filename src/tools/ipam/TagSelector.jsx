import React, { useEffect, useId, useRef, useState } from "react";
import { searchTags, createTag } from "./api.js";
import TagBadge from "./TagBadge.jsx";

export default function TagSelector({ value = [], onChange, allTags: propAllTags, placeholder, disabled = false, canCreate = true, onTagCreated }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [newTagMode, setNewTagMode] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [createError, setCreateError] = useState(null);
  const [newTagColor, setNewTagColor] = useState("#6366f1");
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const listboxId = useId();
  const selectedIds = new Set(value);
  const all = propAllTags || [];

  useEffect(() => {
    const q = query.trim();
    const controller = new AbortController();
    if (!q) {
      setResults(all.filter((tag) => !selectedIds.has(tag.id)));
      setIsSearching(false);
      return () => controller.abort();
    }
    setIsSearching(true);
    const timeoutId = window.setTimeout(async () => {
      try {
        const tags = await searchTags(q, controller.signal);
        if (!controller.signal.aborted) setResults(tags.filter((tag) => !selectedIds.has(tag.id)));
      } catch (error) {
        if (error.name !== "AbortError" && !controller.signal.aborted) setResults([]);
      } finally {
        if (!controller.signal.aborted) setIsSearching(false);
      }
    }, 280);
    return () => { window.clearTimeout(timeoutId); controller.abort(); };
  }, [query, value, all]);

  useEffect(() => { setActiveIndex(-1); }, [results, open]);
  useEffect(() => {
    if (!open) return undefined;
    const handler = (event) => { if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggleTag = async (tagId) => {
    if (disabled) return;
    await onChange(selectedIds.has(tagId) ? value.filter((id) => id !== tagId) : [...value, tagId]);
  };
  const createAndAdd = async () => {
    if (disabled || !canCreate || !newTagName.trim()) return;
    try {
      const created = await createTag({ name: newTagName.trim(), color: newTagColor });
      onTagCreated?.(created);
      await onChange([...value, created.id]);
      setNewTagMode(false); setNewTagName(""); setNewTagColor("#6366f1"); setCreateError(null); setOpen(false);
    } catch (error) { setCreateError(error.message); }
  };
  const onSearchKeyDown = (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActiveIndex((index) => Math.min(index + 1, results.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActiveIndex((index) => Math.max(index - 1, 0)); }
    else if (event.key === "Enter" && activeIndex >= 0) { event.preventDefault(); void toggleTag(results[activeIndex].id); }
    else if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
  };

  return <div className="ip-tag-selector" ref={containerRef}>
    <div className="ip-tag-selector-chips">
      {value.map((tagId) => { const tag = all.find((item) => item.id === tagId); return tag ? <TagBadge key={tagId} tag={tag} size="sm" removable={!disabled} onRemove={(id) => !disabled && onChange(value.filter((item) => item !== id))} /> : null; })}
      {newTagMode ? <div className="ip-tag-selector-new">
        <label className="sr-only" htmlFor={`${listboxId}-new`}>New tag name</label><input id={`${listboxId}-new`} className="tool-input ip-tag-selector-new-input" placeholder="Tag name" value={newTagName} onChange={(event) => setNewTagName(event.target.value)} disabled={disabled} onKeyDown={(event) => { if (event.key === "Enter") void createAndAdd(); if (event.key === "Escape") { setNewTagMode(false); setNewTagName(""); } }} autoFocus />
        <label className="sr-only" htmlFor={`${listboxId}-color`}>Tag color</label><input id={`${listboxId}-color`} type="color" className="ip-tag-selector-color" value={newTagColor} onChange={(event) => setNewTagColor(event.target.value)} disabled={disabled} />
        <button type="button" className="tool-btn tool-btn-sm" onClick={createAndAdd} disabled={disabled}>Create</button><button type="button" className="tool-btn tool-btn-ghost tool-btn-sm" onClick={() => { setNewTagMode(false); setNewTagName(""); }} disabled={disabled}>Cancel</button>
        {createError && <span className="tool-error ip-tag-selector-create-error" role="alert">{createError}</span>}
      </div> : canCreate && <button type="button" className="tool-btn tool-btn-ghost ip-tag-selector-add-btn" onClick={() => setNewTagMode(true)} disabled={disabled}>+ New tag</button>}
    </div>
    <button type="button" className="ip-tag-selector-toggle" onClick={() => setOpen((current) => !current)} disabled={disabled} aria-expanded={open} aria-controls={listboxId}>{open ? "▾" : "▸"} {placeholder || "Tags"}</button>
    {open && <div className="ip-tag-selector-dropdown">
      <label className="sr-only" htmlFor={`${listboxId}-search`}>Search tags</label><input ref={inputRef} id={`${listboxId}-search`} className="tool-input ip-tag-selector-search" placeholder="Search tags…" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={onSearchKeyDown} disabled={disabled} autoFocus role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls={listboxId} aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${results[activeIndex]?.id}` : undefined} />
      {!query.trim() && !newTagMode && results.length > 0 && <div className="ip-tag-selector-hint">Showing all tags ({results.length} available)</div>}
      {isSearching && <div className="ip-tag-selector-empty" role="status">Searching…</div>}
      {!isSearching && results.length === 0 && query.trim() && <div className="ip-tag-selector-empty">No matching tags.</div>}
      <div id={listboxId} role="listbox" aria-label="Available tags">{!isSearching && results.map((tag, index) => <button key={tag.id} id={`${listboxId}-option-${tag.id}`} type="button" role="option" aria-selected={false} className="ip-tag-selector-option" onMouseDown={(event) => { event.preventDefault(); void toggleTag(tag.id); }} onMouseMove={() => setActiveIndex(index)} disabled={disabled}><span className="ip-tag-selector-option-dot" style={{ backgroundColor: tag.color }} /><span className="ip-tag-selector-option-name">{tag.name}</span>{tag.description && <span className="ip-tag-selector-option-desc">{tag.description}</span>}</button>)}</div>
    </div>}
  </div>;
}
