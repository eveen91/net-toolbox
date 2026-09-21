import React, { useEffect, useState } from "react";
import { createAllocatedSubnet, fetchAllocationPlan } from "./api.js";
import TagSelector from "./TagSelector.jsx";
import { allocationDraftToRequest, prefixBounds } from "./allocation.js";

export default function SubnetAllocator({ subnets, tags, onTagCreated, onCreate }) {
  const [parent, setParent] = useState("");
  const [prefix, setPrefix] = useState(24);
  const [plan, setPlan] = useState(null);
  const [selectedCidr, setSelectedCidr] = useState("");
  const [vlan, setVlan] = useState("");
  const [description, setDescription] = useState("");
  const [tagIds, setTagIds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);
  const bounds = prefixBounds(parent);
  const parentSubnets = subnets.filter((subnet) => !subnet.parentId);

  useEffect(() => {
    setPrefix((value) => Math.min(Math.max(value, bounds.min), bounds.max));
    setPlan(null);
    setSelectedCidr("");
    setError(null);
  }, [parent, bounds.min, bounds.max]);

  const findAvailability = async () => {
    setLoading(true);
    setError(null);
    setSelectedCidr("");
    try {
      setPlan(await fetchAllocationPlan(parent, prefix));
    } catch (requestError) {
      setPlan(null);
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const create = async (event) => {
    event.preventDefault();
    if (!selectedCidr || !plan) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createAllocatedSubnet(allocationDraftToRequest({
        parent, cidr: selectedCidr, freshnessToken: plan.freshnessToken, vlan, description, tagIds,
      }));
      onCreate(created);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  };

  return <section className="ip-subnet-allocator" aria-labelledby="allocator-title">
    <header className="ip-allocator-header">
      <h3 id="allocator-title">Allocate subnet</h3>
      <p>Choose a parent and prefix, inspect current occupancy, then create from a verified free block.</p>
    </header>
    <div className="ip-allocator-controls">
      <label className="tool-field">Parent subnet
        <select className="tool-input" value={parent} onChange={(event) => setParent(event.target.value)}>
          <option value="">Select parent subnet</option>
          {parentSubnets.map((subnet) => <option key={subnet.id} value={subnet.cidr}>{subnet.cidr}{subnet.description ? ` — ${subnet.description}` : ""}</option>)}
        </select>
      </label>
      <label className="tool-field">Prefix length
        <input className="tool-input" type="number" inputMode="numeric" min={bounds.min} max={bounds.max} value={prefix} onChange={(event) => setPrefix(Number(event.target.value))} disabled={!parent} />
        <span className="tool-hint">/{bounds.min} through /32</span>
      </label>
      <button type="button" className="tool-btn" disabled={!parent || loading || prefix < bounds.min || prefix > bounds.max} onClick={findAvailability}>{loading ? "Finding availability…" : "Find availability"}</button>
    </div>
    {error && <div className="tool-error" role="alert">{error}</div>}
    {plan && <div className="ip-allocation-results" aria-live="polite">
      <div className="ip-allocation-summary"><strong>{plan.recommendations.length} recommended block{plan.recommendations.length === 1 ? "" : "s"}</strong><span>{plan.totalAddresses.toLocaleString()} addresses per block</span></div>
      {plan.recommendations.length ? <div className="ip-allocation-options" role="radiogroup" aria-label="Recommended free blocks">
        {plan.recommendations.map((cidr) => <button type="button" key={cidr} role="radio" aria-checked={selectedCidr === cidr} className={`ip-allocation-option ${selectedCidr === cidr ? "selected" : ""}`} onClick={() => setSelectedCidr(cidr)}><span>{cidr}</span><small>Available</small></button>)}
      </div> : <div className="tool-empty">No /{prefix} blocks remain in {plan.parent}. Choose a smaller allocation or another parent.</div>}
      <div className="ip-allocation-occupied"><h4>Occupied ranges</h4>{plan.occupiedRanges.length ? <ul>{plan.occupiedRanges.map((range, index) => <li key={`${range.source}-${range.start}-${index}`}><span>{range.start} — {range.end}</span><small>{range.cidr || range.source.replace("_", " ")}</small></li>)}</ul> : <p>No recorded subnets, addresses, or DHCP pools occupy this parent.</p>}</div>
      {selectedCidr && <form className="ip-allocation-create" onSubmit={create}>
        <h4>Create {selectedCidr}</h4>
        <label className="tool-field">VLAN<input className="tool-input" type="number" inputMode="numeric" min="1" max="4094" value={vlan} onChange={(event) => setVlan(event.target.value)} /></label>
        <label className="tool-field">Description<textarea className="tool-input" maxLength="500" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <div className="tool-field"><span>Tags</span><TagSelector value={tagIds} onChange={setTagIds} allTags={tags} placeholder="Select existing tags" disabled={creating} onTagCreated={onTagCreated} /></div>
        <button className="tool-btn" disabled={creating}>{creating ? "Creating subnet…" : "Create subnet"}</button>
      </form>}
    </div>}
  </section>;
}
