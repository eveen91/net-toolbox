import React, { useEffect, useState } from "react";
import { addScanExclude, listScanExcludes, removeScanExclude } from "./api.js";

export default function ScanExcludeManager({ subnetId }) {
  const [excludes, setExcludes] = useState([]);
  const [newAddress, setNewAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    setLoading(true);
    listScanExcludes(subnetId)
      .then(setExcludes)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, [subnetId]);

  const addExclude = async (event) => {
    event.preventDefault();
    if (!newAddress.trim()) return;
    setError(null);
    try {
      setExcludes(await addScanExclude(subnetId, newAddress.trim()));
      setNewAddress("");
    } catch (addError) {
      setError(addError.message);
    }
  };

  const removeExclude = async (id) => {
    setError(null);
    try {
      setExcludes(await removeScanExclude(subnetId, id));
    } catch (removeError) {
      setError(removeError.message);
    }
  };

  return (
    <div className="ip-scan-excludes">
      <div className="tool-hint">Scan excludes</div>
      {error && <div className="tool-error">{error}</div>}
      {!loading && excludes.length === 0 && <div className="tool-hint">No excluded addresses.</div>}
      {excludes.length > 0 && (
        <ul className="ip-scan-exclude-list">
          {excludes.map((exclude) => (
            <li key={exclude.id}>
              <span className="ip-mono">{exclude.address}</span>
              <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => removeExclude(exclude.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="ip-add-row" onSubmit={addExclude}>
        <input
          className="tool-input"
          style={{ maxWidth: 160 }}
          placeholder="10.0.1.10"
          aria-label="Address to exclude from scans"
          value={newAddress}
          onChange={(event) => setNewAddress(event.target.value)}
        />
        <button className="tool-btn tool-btn-primary" type="submit" disabled={!newAddress.trim()}>Add</button>
      </form>
    </div>
  );
}
