import React, { useEffect, useState } from "react";
import "./ipam.css";
import SubnetSearch from "./SubnetSearch.jsx";
import AddSubnetForm from "./AddSubnetForm.jsx";
import {
  formatVlan,
  formatTimestamp,
  utilizationPercent,
  STATUS_LABELS,
  buildSubnetTree,
  ancestorChain,
} from "./logic.js";
import {
  listSubnets,
  getSubnet,
  createSubnet,
  updateSubnet,
  deleteSubnet,
  addAddress,
  updateAddress,
  deleteAddress,
} from "./api.js";

const STATUS_PILL_CLASS = {
  used: "tool-pill-muted",
  free: "tool-pill-ok",
  reserved: "tool-pill-warn",
};

function UtilizationBar({ subnet }) {
  const total = subnet.totalAddresses || 1;
  const usedPct = Math.min(100, (subnet.usedCount / total) * 100);
  const reservedPct = Math.min(100 - usedPct, (subnet.reservedCount / total) * 100);
  const freePct = Math.min(100 - usedPct - reservedPct, (subnet.freeCount / total) * 100);
  return (
    <div className="ip-util-bar" title={`${utilizationPercent(subnet)}% allocated (used + reserved)`}>
      <div className="ip-util-seg ip-util-used" style={{ width: `${usedPct}%` }} />
      <div className="ip-util-seg ip-util-reserved" style={{ width: `${reservedPct}%` }} />
      <div className="ip-util-seg ip-util-free" style={{ width: `${freePct}%` }} />
    </div>
  );
}

/** Row for one recorded address: view mode + an inline edit mode, plus a delete confirm step. */
function AddressRow({ subnetId, addr, onUpdated, onError }) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    address: addr.address,
    status: addr.status,
    hostname: addr.hostname || "",
    description: addr.description || "",
  });

  const startEdit = () => {
    setDraft({
      address: addr.address,
      status: addr.status,
      hostname: addr.hostname || "",
      description: addr.description || "",
    });
    setEditing(true);
  };

  const save = async () => {
    onError(null);
    setSaving(true);
    try {
      const updated = await updateAddress(
        subnetId,
        addr.id,
        draft.address.trim(),
        draft.status,
        draft.hostname.trim() || null,
        draft.description.trim() || null
      );
      onUpdated(updated);
      setEditing(false);
    } catch (e) {
      onError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    onError(null);
    setSaving(true);
    try {
      const updated = await deleteAddress(subnetId, addr.id);
      onUpdated(updated);
    } catch (e) {
      onError(e.message);
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <tr>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.address}
            onChange={(e) => setDraft({ ...draft, address: e.target.value })}
          />
        </td>
        <td>
          <select
            className="tool-input ip-row-input"
            value={draft.status}
            onChange={(e) => setDraft({ ...draft, status: e.target.value })}
          >
            {Object.entries(STATUS_LABELS).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </td>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.hostname}
            onChange={(e) => setDraft({ ...draft, hostname: e.target.value })}
            placeholder="hostname"
          />
        </td>
        <td>
          <input
            className="tool-input ip-row-input"
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="description"
          />
        </td>
        <td className="ip-actions-cell">
          <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setEditing(false)} disabled={saving}>
            Cancel
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td className="ip-mono">{addr.address}</td>
      <td>
        <span className={`tool-pill ${STATUS_PILL_CLASS[addr.status]}`}>{STATUS_LABELS[addr.status]}</span>
      </td>
      <td>{addr.hostname || "—"}</td>
      <td>{addr.description || "—"}</td>
      <td className="ip-actions-cell">
        {confirmingDelete ? (
          <>
            <button className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger" onClick={remove} disabled={saving}>
              {saving ? "…" : "Confirm"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setConfirmingDelete(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEdit}>
              Edit
            </button>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => setConfirmingDelete(true)}>
              Delete
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

function AddAddressForm({ subnetId, onAdded, onError }) {
  const [address, setAddress] = useState("");
  const [status, setStatus] = useState("used");
  const [hostname, setHostname] = useState("");
  const [description, setDescription] = useState("");
  const [adding, setAdding] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!address.trim()) return;
    onError(null);
    setAdding(true);
    try {
      const updated = await addAddress(subnetId, address.trim(), status, hostname.trim() || null, description.trim() || null);
      onAdded(updated);
      setAddress("");
      setHostname("");
      setDescription("");
      setStatus("used");
    } catch (e2) {
      onError(e2.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <form className="ip-add-row" onSubmit={submit}>
      <input
        className="tool-input"
        style={{ maxWidth: 160 }}
        placeholder="10.0.1.10"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
      />
      <select className="tool-input" style={{ maxWidth: 130 }} value={status} onChange={(e) => setStatus(e.target.value)}>
        {Object.entries(STATUS_LABELS).map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <input
        className="tool-input"
        placeholder="hostname (optional)"
        value={hostname}
        onChange={(e) => setHostname(e.target.value)}
      />
      <input
        className="tool-input"
        placeholder="description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <button className="tool-btn tool-btn-primary" type="submit" disabled={adding || !address.trim()}>
        {adding ? "Adding…" : "Add"}
      </button>
    </form>
  );
}

function SubnetDetail({ subnet, subnets, deleting, onDelete, onDetailUpdated, onSelectSubnet }) {
  const [editingHeader, setEditingHeader] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [headerDraft, setHeaderDraft] = useState({
    cidr: subnet.cidr,
    vlan: subnet.vlan ?? "",
    description: subnet.description || "",
  });
  const [headerError, setHeaderError] = useState(null);
  const [headerSaving, setHeaderSaving] = useState(false);
  const [rowError, setRowError] = useState(null);

  useEffect(() => {
    setConfirmingDelete(false);
    setEditingHeader(false);
    setHeaderError(null);
    setRowError(null);
  }, [subnet.id]);

  const startEditHeader = () => {
    setHeaderDraft({ cidr: subnet.cidr, vlan: subnet.vlan ?? "", description: subnet.description || "" });
    setHeaderError(null);
    setEditingHeader(true);
  };

  const saveHeader = async () => {
    setHeaderError(null);
    setHeaderSaving(true);
    try {
      const vlan = headerDraft.vlan === "" ? null : Number(headerDraft.vlan);
      const updated = await updateSubnet(subnet.id, headerDraft.cidr.trim(), vlan, headerDraft.description.trim() || null);
      onDetailUpdated(updated);
      setEditingHeader(false);
    } catch (e) {
      setHeaderError(e.message);
    } finally {
      setHeaderSaving(false);
    }
  };

  const unallocated = subnet.totalAddresses - subnet.recordedCount;
  const ancestors = ancestorChain(subnets, subnet.id);
  const children = subnets.filter((s) => s.parentId === subnet.id);

  return (
    <>
      {ancestors.length > 0 && (
        <div className="ip-breadcrumb">
          {ancestors.map((a) => (
            <React.Fragment key={a.id}>
              <button className="ip-breadcrumb-link" onClick={() => onSelectSubnet(a.id)}>
                {a.cidr}
              </button>
              <span className="ip-breadcrumb-sep">›</span>
            </React.Fragment>
          ))}
          <span>{subnet.cidr}</span>
        </div>
      )}
      <div className="tool-section-title">
        {editingHeader ? (
          <span className="ip-header-edit">
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 160 }}
              value={headerDraft.cidr}
              onChange={(e) => setHeaderDraft({ ...headerDraft, cidr: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              style={{ maxWidth: 100 }}
              placeholder="VLAN"
              value={headerDraft.vlan}
              onChange={(e) => setHeaderDraft({ ...headerDraft, vlan: e.target.value })}
            />
            <input
              className="tool-input ip-row-input"
              placeholder="description"
              value={headerDraft.description}
              onChange={(e) => setHeaderDraft({ ...headerDraft, description: e.target.value })}
            />
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={saveHeader} disabled={headerSaving}>
              {headerSaving ? "Saving…" : "Save"}
            </button>
            <button
              className="tool-btn tool-btn-ghost ip-row-btn"
              onClick={() => setEditingHeader(false)}
              disabled={headerSaving}
            >
              Cancel
            </button>
          </span>
        ) : (
          <>
            {subnet.cidr}
            <span className="tool-hint">
              {formatVlan(subnet.vlan)} · {subnet.description || "no description"}
              {children.length > 0
                ? ` · ${children.length} nested subnet${children.length !== 1 ? "s" : ""}`
                : ""}{" "}
              · saved {formatTimestamp(subnet.updatedAt)}
            </span>
            <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={startEditHeader}>
              Edit
            </button>
          </>
        )}
        {!editingHeader &&
          (confirmingDelete ? (
            <span className="ip-delete-confirm">
              <span className="tool-hint">Delete subnet "{subnet.cidr}"? This can't be undone.</span>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn ip-row-btn-danger"
                onClick={() => {
                  setConfirmingDelete(false);
                  onDelete();
                }}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                className="tool-btn tool-btn-ghost ip-row-btn"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              className="tool-btn tool-btn-ghost ip-row-btn ip-delete-subnet-btn"
              onClick={() => setConfirmingDelete(true)}
              disabled={deleting}
            >
              Delete subnet
            </button>
          ))}
      </div>
      {headerError && <div className="tool-error">{headerError}</div>}

      <UtilizationBar subnet={subnet} />
      <div className="tool-summary">
        <div className="tool-stat">
          <div className="n">{subnet.totalAddresses.toLocaleString()}</div>
          <div className="l">Total addresses</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.usedCount}</div>
          <div className="l">Used</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.reservedCount}</div>
          <div className="l">Reserved</div>
        </div>
        <div className="tool-stat">
          <div className="n">{subnet.freeCount}</div>
          <div className="l">Free (recorded)</div>
        </div>
        <div className="tool-stat">
          <div className="n">{unallocated.toLocaleString()}</div>
          <div className="l">Not recorded</div>
        </div>
      </div>

      {children.length > 0 && (
        <>
          <h3 className="ip-section-sub-title">
            Nested subnets <span className="tool-hint">{children.length}</span>
          </h3>
          <div className="tool-table-wrap ip-table-wrap-full">
            <table className="tool-table">
              <thead>
                <tr>
                  <th>CIDR</th>
                  <th>VLAN</th>
                  <th>Description</th>
                  <th>Recorded</th>
                </tr>
              </thead>
              <tbody>
                {children.map((c) => (
                  <tr key={c.id} className="ip-child-row" onClick={() => onSelectSubnet(c.id)}>
                    <td className="ip-mono">{c.cidr}</td>
                    <td>{formatVlan(c.vlan)}</td>
                    <td>{c.description || "—"}</td>
                    <td>
                      {c.usedCount}u · {c.reservedCount}r · {c.freeCount}f
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="ip-section-sub-title">Addresses</h3>
      {rowError && <div className="tool-error">{rowError}</div>}
      <AddAddressForm subnetId={subnet.id} onAdded={onDetailUpdated} onError={setRowError} />

      {subnet.addresses.length === 0 ? (
        <div className="tool-empty">No addresses recorded yet — add one above.</div>
      ) : (
        <div className="tool-table-wrap ip-table-wrap-full">
          <table className="tool-table">
            <thead>
              <tr>
                <th>Address</th>
                <th>Status</th>
                <th>Hostname</th>
                <th>Description</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {subnet.addresses.map((addr) => (
                <AddressRow
                  key={addr.id}
                  subnetId={subnet.id}
                  addr={addr}
                  onUpdated={onDetailUpdated}
                  onError={setRowError}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/** One row of the subnet tree, rendered recursively for its children when expanded. */
function SubnetNode({ node, depth, selectedId, collapsedIds, onToggleCollapse, onSelect }) {
  const hasChildren = node.children.length > 0;
  const collapsed = collapsedIds.has(node.id);

  return (
    <>
      <button
        className={`ip-subnet-item ${selectedId === node.id ? "active" : ""}`}
        style={{ paddingLeft: 10 + depth * 16 }}
        onClick={() => onSelect(node.id)}
      >
        <span className="ip-subnet-item-top">
          {hasChildren ? (
            <span
              className="ip-subnet-toggle"
              onClick={(e) => {
                e.stopPropagation();
                onToggleCollapse(node.id);
              }}
            >
              {collapsed ? "▸" : "▾"}
            </span>
          ) : (
            <span className="ip-subnet-toggle ip-subnet-toggle-spacer" />
          )}
          <span className="ip-subnet-cidr">{node.cidr}</span>
          {node.vlan != null && <span className="ip-subnet-vlan">VLAN {node.vlan}</span>}
        </span>
        <span className="ip-subnet-item-bottom">
          <span className="tool-hint">{node.description || "no description"}</span>
          <span className="ip-subnet-counts">
            {node.usedCount}u · {node.reservedCount}r · {node.freeCount}f
          </span>
        </span>
      </button>
      {hasChildren &&
        !collapsed &&
        node.children.map((child) => (
          <SubnetNode
            key={child.id}
            node={child}
            depth={depth + 1}
            selectedId={selectedId}
            collapsedIds={collapsedIds}
            onToggleCollapse={onToggleCollapse}
            onSelect={onSelect}
          />
        ))}
    </>
  );
}

export default function Ipam() {
  const [subnets, setSubnets] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);

  const [newCidr, setNewCidr] = useState("");
  const [newVlan, setNewVlan] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [collapsedIds, setCollapsedIds] = useState(() => new Set());

  const refreshList = async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listSubnets();
      setSubnets(data);
    } catch (e) {
      setListError(e.message);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
  }, []);

  const toggleCollapse = (id) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectSubnet = async (id) => {
    setSelectedId(id);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await getSubnet(id);
      setSelectedDetail(detail);
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDetailUpdated = (detail) => {
    setSelectedDetail(detail);
    // A CIDR edit (or an address change) can shift the whole nesting tree
    // (this subnet's parent, or other subnets' parents, may have changed) —
    // a full refetch keeps parentId accurate everywhere, not just here.
    refreshList();
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newCidr.trim()) return;
    setCreateError(null);
    setCreating(true);
    try {
      const vlan = newVlan.trim() === "" ? null : Number(newVlan);
      const created = await createSubnet(newCidr.trim(), vlan, newDescription.trim() || null);
      setNewCidr("");
      setNewVlan("");
      setNewDescription("");
      await refreshList();
      await selectSubnet(created.id);
    } catch (e2) {
      setCreateError(e2.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteSubnet(selectedId);
      setSelectedId(null);
      setSelectedDetail(null);
      await refreshList();
    } catch (e) {
      setDetailError(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <div className="nt-tool-header">
        <h2>IPAM</h2>
        <p>Track subnets with a VLAN tag, then record individual IP addresses as used, free, or reserved.</p>
      </div>

      <div className="tool-layout">
        <div className="tool-panel">
          {/* TEMPORARY for this session only — AddSubnetForm is being tried
              out here in place of the old inline form; Session 3 moves it
              into the new header row next to SubnetSearch. */}
          <AddSubnetForm
            onCreated={async (created) => {
              await refreshList();
              await selectSubnet(created.id);
            }}
          />

          <div className="ip-divider" />
          {/* TEMPORARY for this session only — SubnetSearch is being tried
              out here; Session 3 moves it into the new full-width layout
              and removes the tree below it. */}
          <SubnetSearch subnets={subnets} selectedId={selectedId} onSelect={selectSubnet} />
          <div className="ip-divider" />
          <div className="ip-section-label">
            Subnets <span className="tool-hint">{subnets.length}</span>
            <button className="tool-btn tool-btn-ghost ip-refresh" onClick={refreshList} disabled={listLoading}>
              {listLoading ? "…" : "Refresh"}
            </button>
          </div>
          {listError && <div className="tool-error">{listError}</div>}
          <div className="ip-subnet-list">
            {!listLoading && subnets.length === 0 && !listError && (
              <div className="tool-hint">No subnets yet — add one above.</div>
            )}
            {buildSubnetTree(subnets).map((node) => (
              <SubnetNode
                key={node.id}
                node={node}
                depth={0}
                selectedId={selectedId}
                collapsedIds={collapsedIds}
                onToggleCollapse={toggleCollapse}
                onSelect={selectSubnet}
              />
            ))}
          </div>
        </div>

        <div className="tool-panel">
          {!selectedId && <div className="tool-empty">Select a subnet from the list to view and manage its addresses.</div>}

          {selectedId && detailLoading && <div className="tool-empty">Loading…</div>}

          {selectedId && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}

          {selectedId && !detailLoading && selectedDetail && (
            <SubnetDetail
              subnet={selectedDetail}
              subnets={subnets}
              deleting={deleting}
              onDelete={handleDelete}
              onDetailUpdated={handleDetailUpdated}
              onSelectSubnet={selectSubnet}
            />
          )}
        </div>
      </div>
    </div>
  );
}