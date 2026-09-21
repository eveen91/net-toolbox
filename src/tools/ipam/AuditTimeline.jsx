import React, { useId, useState } from "react";
import "./ipam.css";
import {
  AUDIT_EVENT_TYPES,
  auditDiffRows,
  auditEventLabel,
  auditEventTone,
  auditPageCount,
  formatAuditValue,
} from "./audit.js";
import { formatTimestamp } from "./logic.js";
import useAuditHistory from "./useAuditHistory.js";

function AuditDiff({ entry }) {
  const rows = auditDiffRows(entry.oldValue, entry.newValue);
  if (rows.length === 0) return <div className="tool-empty audit-diff-empty">No field-level changes recorded.</div>;
  return (
    <div className="audit-diff">
      <table>
        <caption className="sr-only">Old and new values for {auditEventLabel(entry.changeType)}</caption>
        <thead><tr><th scope="col">Field</th><th scope="col">Old value</th><th scope="col">New value</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field}>
              <th scope="row" className="audit-field">{row.field}</th>
              <td className="audit-old">{formatAuditValue(row.oldValue)}</td>
              <td className="audit-new">{formatAuditValue(row.newValue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AuditTimeline({
  subnetId,
  addressId,
  title = "History",
  description,
  pageSize = 25,
  compact = false,
  showTarget = true,
  className = "",
  adminExport = false,
}) {
  const history = useAuditHistory({ subnetId, addressId, pageSize, adminExport });
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const filterId = useId();
  const pageCount = auditPageCount(history.total, history.pageSize);
  const firstEntry = history.total === 0 ? 0 : (history.page - 1) * history.pageSize + 1;
  const lastEntry = Math.min(history.page * history.pageSize, history.total);

  const toggleEntry = (entryId) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  };

  return (
    <section className={`audit-history${compact ? " audit-history-compact" : ""}${className ? ` ${className}` : ""}`} aria-labelledby={`${filterId}-title`}>
      <div className="audit-header">
        <div>
          <h3 id={`${filterId}-title`}>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        <button type="button" className="tool-btn tool-btn-ghost" onClick={() => history.exportCsv(`ipam-audit-${addressId || subnetId || "all"}.csv`)} disabled={history.exporting}>
          {history.exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>

      <div className="audit-filter-bar" aria-label="Audit history filters">
        <label className="audit-filter-field" htmlFor={`${filterId}-start`}>
          <span>From date</span>
          <input id={`${filterId}-start`} className="tool-input" type="date" value={history.startDate} max={history.endDate || undefined} onChange={(event) => history.setStartDate(event.target.value)} />
        </label>
        <label className="audit-filter-field" htmlFor={`${filterId}-end`}>
          <span>To date</span>
          <input id={`${filterId}-end`} className="tool-input" type="date" value={history.endDate} min={history.startDate || undefined} onChange={(event) => history.setEndDate(event.target.value)} />
        </label>
        <label className="audit-filter-field" htmlFor={`${filterId}-event`}>
          <span>Event type</span>
          <select id={`${filterId}-event`} className="tool-input" value={history.eventType} onChange={(event) => history.setEventType(event.target.value)}>
            <option value="">All event types</option>
            {AUDIT_EVENT_TYPES.map((eventType) => <option key={eventType} value={eventType}>{auditEventLabel(eventType)}</option>)}
          </select>
        </label>
        <button type="button" className="tool-btn tool-btn-ghost audit-refresh" onClick={history.refresh} disabled={history.loading} aria-label="Refresh audit history">
          {history.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div aria-live="polite" aria-atomic="true">
        {history.loading && <div className="tool-empty">Loading history…</div>}
        {history.error && <div className="tool-error" role="alert">History failed to load: {history.error}</div>}
        {!history.loading && !history.error && history.entries.length === 0 && <div className="tool-empty">No history matches these filters.</div>}
      </div>

      {!history.loading && !history.error && history.entries.length > 0 && (
        <>
          <div className="audit-timeline">
            {history.entries.map((entry) => {
              const expanded = expandedIds.has(entry.id);
              const panelId = `${filterId}-diff-${entry.id}`;
              return (
                <article key={entry.id} className="audit-entry">
                  <button type="button" className="audit-entry-header" onClick={() => toggleEntry(entry.id)} aria-expanded={expanded} aria-controls={panelId}>
                    <span className={`audit-type-badge audit-type-${auditEventTone(entry.changeType)}`}>{auditEventLabel(entry.changeType)}</span>
                    {showTarget && <span className="audit-target"><span className="audit-ip">{entry.ipAddress || entry.subnetCidr || "Inventory"}</span>{entry.ipAddress && entry.subnetCidr && <span className="audit-subnet">{entry.subnetCidr}</span>}</span>}
                    <span className="audit-desc">{entry.description || "No description provided"}</span>
                    <span className="audit-user"><span className="sr-only">User: </span>{entry.username || "system"}</span>
                    <time className="audit-time" dateTime={entry.createdAt}><span className="sr-only">Time: </span>{formatTimestamp(entry.createdAt)}</time>
                    <span className="audit-expand" aria-hidden="true">{expanded ? "−" : "+"}</span>
                  </button>
                  {expanded && <div className="audit-entry-body" id={panelId}><AuditDiff entry={entry} /></div>}
                </article>
              );
            })}
          </div>
          <nav className="audit-pagination" aria-label="Audit history pages">
            <span>{firstEntry}–{lastEntry} of {history.total}</span>
            <div>
              <button type="button" className="tool-btn tool-btn-ghost" onClick={() => history.setPage((page) => page - 1)} disabled={history.page === 1}>Previous</button>
              <span>Page {history.page} of {pageCount}</span>
              <button type="button" className="tool-btn tool-btn-ghost" onClick={() => history.setPage((page) => page + 1)} disabled={history.page >= pageCount}>Next</button>
            </div>
          </nav>
        </>
      )}
    </section>
  );
}
