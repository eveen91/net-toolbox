import React, { useState } from "react";
import { getIpamSettings, updateIpamSettings } from "./api.js";

export default function IpamSettingsPopover() {
  const [open, setOpen] = useState(false);
  const [scanConcurrencyLimit, setScanConcurrencyLimit] = useState(null);
  const [bounds, setBounds] = useState({ min: 1, max: 256 });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const openSettings = async () => {
    setOpen(true);
    setError(null);
    try {
      const result = await getIpamSettings();
      setScanConcurrencyLimit(result.scanConcurrencyLimit);
      setBounds({ min: result.scanConcurrencyMin, max: result.scanConcurrencyMax });
    } catch (loadError) {
      setError(loadError.message);
    }
  };

  const saveSettings = async () => {
    setError(null);
    setSaving(true);
    try {
      await updateIpamSettings(Number(scanConcurrencyLimit));
      setOpen(false);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ip-settings-wrap">
      <button
        className="tool-btn tool-btn-ghost ip-row-btn"
        onClick={openSettings}
        title="Autodiscovery settings"
        aria-label="Autodiscovery settings"
      >
        ⚙
      </button>
      {open && (
        <div className="tool-popover ip-settings-popover">
          <div className="tool-hint">Autodiscovery settings</div>
          {scanConcurrencyLimit === null ? (
            <div className="tool-hint">Loading…</div>
          ) : (
            <>
              <label className="tool-hint" htmlFor="ipam-scan-concurrency">Simultaneous scans (hosts pinged at once)</label>
              <input
                id="ipam-scan-concurrency"
                className="tool-input"
                type="number"
                min={bounds.min}
                max={bounds.max}
                value={scanConcurrencyLimit}
                onChange={(event) => setScanConcurrencyLimit(event.target.value)}
              />
              <div className="tool-hint">Range: {bounds.min}–{bounds.max}</div>
              {error && <div className="tool-error">{error}</div>}
              <div className="ip-settings-actions">
                <button className="tool-btn tool-btn-primary" onClick={saveSettings} disabled={saving}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button className="tool-btn tool-btn-ghost" onClick={() => setOpen(false)} disabled={saving}>Cancel</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
