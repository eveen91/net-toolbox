import React, { useEffect, useState } from "react";
import {
  createRangeReservation,
  deleteRangeReservation,
  getRangeReservations,
  updateRangeReservation,
} from "./api.js";

function isValidIpv4(value) {
  const parts = value.trim().split(".");
  return parts.length === 4 && parts.every((part) => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255);
}

function ipToNumber(value) {
  return value.split(".").reduce((total, part) => total * 256 + Number(part), 0);
}

function emptyDraft() {
  return { start_ip: "", end_ip: "", status: "active", label: "", description: "" };
}

export default function RangeReservationManager({ subnetId, onReservationsChanged }) {
  const [reservations, setReservations] = useState([]);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadReservations = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRangeReservations(subnetId);
      setReservations(data);
      onReservationsChanged?.(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setDraft(null);
    loadReservations();
  }, [subnetId]);

  const save = async (event) => {
    event.preventDefault();
    if (!draft || saving) return;
    if (!isValidIpv4(draft.start_ip) || !isValidIpv4(draft.end_ip)) {
      setError("Start and end IP must be valid IPv4 addresses");
      return;
    }
    if (ipToNumber(draft.start_ip) > ipToNumber(draft.end_ip)) {
      setError("Start IP must be less than or equal to end IP");
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      start_ip: draft.start_ip.trim(),
      end_ip: draft.end_ip.trim(),
      allocation_type: "reserved_range",
      status: draft.status,
      label: draft.label.trim() || null,
      description: draft.description.trim() || null,
    };
    try {
      if (draft.id) await updateRangeReservation(subnetId, draft.id, payload);
      else await createRangeReservation(subnetId, payload);
      setDraft(null);
      await loadReservations();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (reservation) => {
    if (!window.confirm(`Delete reservation ${reservation.start_ip}–${reservation.end_ip}?`)) return;
    setError(null);
    try {
      await deleteRangeReservation(subnetId, reservation.id);
      await loadReservations();
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  if (loading) return <div className="tool-empty">Loading range reservations...</div>;

  return (
    <div>
      <div className="ip-add-row">
        <button type="button" className="tool-btn tool-btn-primary" onClick={() => setDraft(emptyDraft())}>+ Reserve range</button>
      </div>
      {error && <div className="tool-error" role="alert">{error}</div>}
      {reservations.length === 0 ? <div className="tool-empty">No range reservations defined</div> : (
        <div className="tool-table-wrap ip-table-wrap-full"><table className="tool-table">
          <thead><tr><th>Range</th><th>Label</th><th>Status</th><th>Description</th><th className="ip-actions-cell">Actions</th></tr></thead>
          <tbody>{reservations.map((reservation) => <tr key={reservation.id}>
            <td className="ip-mono">{reservation.start_ip} – {reservation.end_ip}</td>
            <td>{reservation.label || "—"}</td>
            <td><span className={`tool-pill ${reservation.status === "active" ? "tool-pill-warn" : "tool-pill-muted"}`}>{reservation.status}</span></td>
            <td>{reservation.description || "—"}</td>
            <td className="ip-actions-cell"><div className="ip-actions-inner">
              <button type="button" className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setDraft({ ...reservation })}>Edit</button>
              <button type="button" className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger" onClick={() => remove(reservation)}>Delete</button>
            </div></td>
          </tr>)}</tbody>
        </table></div>
      )}
      {draft && <div className="tool-modal-overlay" onClick={() => !saving && setDraft(null)}><div className="tool-modal" onClick={(event) => event.stopPropagation()}>
        <div className="tool-modal-header"><h3>{draft.id ? "Edit range reservation" : "Reserve address range"}</h3><button type="button" className="tool-modal-close" onClick={() => setDraft(null)} disabled={saving}>×</button></div>
        <form onSubmit={save}>
          <div className="tool-field"><label className="tool-label">Start IP</label><input autoFocus required className="tool-input" value={draft.start_ip} onChange={(event) => setDraft({ ...draft, start_ip: event.target.value })} /></div>
          <div className="tool-field"><label className="tool-label">End IP</label><input required className="tool-input" value={draft.end_ip} onChange={(event) => setDraft({ ...draft, end_ip: event.target.value })} /></div>
          <div className="tool-field"><label className="tool-label">Status</label><select className="tool-input" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="active">Active</option><option value="released">Released</option></select></div>
          <div className="tool-field"><label className="tool-label">Label <span className="tool-hint">optional</span></label><input className="tool-input" value={draft.label || ""} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></div>
          <div className="tool-field"><label className="tool-label">Description <span className="tool-hint">optional</span></label><input className="tool-input" value={draft.description || ""} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></div>
          <div className="tool-actions"><button type="submit" className="tool-btn tool-btn-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button><button type="button" className="tool-btn tool-btn-ghost" onClick={() => setDraft(null)} disabled={saving}>Cancel</button></div>
        </form>
      </div></div>}
    </div>
  );
}
