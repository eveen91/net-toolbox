import React, { useState } from "react";
import {
  fetchSubnetAllocation,
} from "./api.js";

export default function SubnetAllocator({ subnets, onCreate }) {
  const [parentCidr, setParentCidr] = useState("");
  const [prefix, setPrefix] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [allocation, setAllocation] = useState(null);

  const parentSubnets = subnets.filter((s) => !s.parentId);

  const handleFindNext = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSubnetAllocation(parentCidr, prefix);
      setAllocation(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ip-subnet-allocator">
      <h3>Subnet Allocator</h3>
      <p>Find available contiguous subnets within a parent CIDR.</p>

      <div className="tool-section">
        <div className="tool-field">
          <label>Parent CIDR</label>
          <select
            className="tool-input"
            value={parentCidr}
            onChange={(e) => setParentCidr(e.target.value)}
          >
            <option value="">- Select parent subnet -</option>
            {parentSubnets.map((s) => (
              <option key={s.id} value={s.cidr}>
                {s.cidr} ({s.name})
              </option>
            ))}
          </select>
        </div>

        <div className="tool-field">
          <label>Subnet prefix</label>
          <div className="ip-prefix-buttons">
            {[24, 25, 26, 27, 28, 29, 30].map((p) => (
              <button
                key={p}
                className={`tool-btn tool-btn-ghost ${prefix === p ? "active" : ""}`}
                onClick={() => setPrefix(p)}
              >
                /{p}
              </button>
            ))}
          </div>
        </div>

        <button
          className="tool-btn"
          disabled={!parentCidr || loading}
          onClick={handleFindNext}
        >
          Find Next Available Subnet
        </button>
      </div>

      {loading && <div className="tool-loading">Finding next subnet...</div>}

      {error && <div className="tool-error">{error}</div>}

      {allocation && (
        <div className="ip-allocation-results">
          <h4>Allocation Recommendation</h4>

          <p>
            In <strong>{parentCidr}</strong>, the next available /{prefix} subnet is:
          </p>

          <div className="allocation-card">
            <p>
              <strong>Recommended:</strong> {allocation.recommendation || "None available"}
            </p>

            {allocation.availableFrom && (
              <p>
                Available range:<br />
                {allocation.availableFrom} - {allocation.availableTo}
              </p>
            )}

            <p>
              Total addresses: {allocation.totalAddresses.toLocaleString()}
            </p>

            {allocation.nextAvailableAfter && (
              <p>
                Next available after: {allocation.nextAvailableAfter}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
