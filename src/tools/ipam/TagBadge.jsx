import React from "react";

/**
 * Small colored badge displaying a tag name.
 *
 * Props:
 *   tag    – { id, name, color } or full tag object
 *   size   – "sm" | "md" (default "md")
 *   removable – if true, renders a close button
 *   onRemove – callback when remove is clicked
 */
export default function TagBadge({ tag, size = "md", removable = false, onRemove }) {
  const name = typeof tag === "string" ? tag : tag.name;
  const color = tag.color || "#6366f1";
  const id = tag.id;

  const sizeClass = size === "sm" ? "ip-tag-badge-sm" : "ip-tag-badge";

  return (
    <span
      className={`ip-tag-badge ${sizeClass}`}
      style={{
        backgroundColor: color + "22",
        color: color,
        borderColor: color + "66",
      }}
      title={tag.description || name}
    >
      <span className="ip-tag-badge-dot" style={{ backgroundColor: color }} />
      <span className="ip-tag-badge-name">{name}</span>
      {removable && onRemove && (
        <button
          type="button"
          className="ip-tag-badge-remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(id);
          }}
          aria-label={`Remove tag ${name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
