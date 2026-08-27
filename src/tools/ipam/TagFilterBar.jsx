import React from "react";
import TagBadge from "./TagBadge.jsx";

/**
 * Horizontal bar of active tag filter chips.
 *
 * Shows the currently applied tag filters with delete buttons. Clicking the
 * "X" on a chip removes that filter.
 *
 * Props:
 *   tags     – array of tag objects ({ id, name, color, description })
 *   onRemove – (tagId) => void
 */
export default function TagFilterBar({ tags = [], onRemove }) {
  if (!tags || tags.length === 0) return null;

  return (
    <div className="ip-tag-filter-bar">
      <span className="ip-tag-filter-bar-label">Filtered by:</span>
      {tags.map((tag) => (
        <TagBadge
          key={tag.id}
          tag={tag}
          size="sm"
          removable
          onRemove={onRemove}
        />
      ))}
      <button
        type="button"
        className="tool-btn tool-btn-ghost ip-tag-filter-bar-clear"
        onClick={() => tags.forEach((t) => onRemove(t.id))}
      >
        Clear all
      </button>
    </div>
  );
}
