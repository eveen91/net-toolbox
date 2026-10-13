import React from "react";
import AddSubnetForm from "./AddSubnetForm.jsx";
import IpamSettingsPopover from "./IpamSettingsPopover.jsx";
import SubnetSearch from "./SubnetSearch.jsx";
import ViewTabs from "../../components/ViewTabs.jsx";

export default function IpamToolbar({ subnets, selectedId, tags, selectedTagIds, onTagFilterChange, onSelect, onCreated, viewMode, onViewModeChange, permissions = { read: true, write: true, scan: true, admin: true } }) {
  const planning = viewMode === "allocator" || viewMode === "resubnet";
  const views = [{ id: "search", label: "Subnets" }, { id: "dashboard", label: "Overview" },
    { id: "planning", label: "Planning" }, { id: "quality", label: "Data quality" }, { id: "archive", label: "Archive" }];
  const changeView = (id) => onViewModeChange(id === "planning" ? (permissions.write ? "allocator" : "resubnet") : id);
  return <div className="ip-module-toolbar">
    <div className="ip-module-actions">
      {permissions.write && <AddSubnetForm onCreated={onCreated} />}
      {permissions.write && <button type="button" className="tool-btn tool-btn-ghost" onClick={() => onViewModeChange("import")}>Import</button>}
      {permissions.admin && <IpamSettingsPopover />}
    </div>
    <ViewTabs items={views} value={planning ? "planning" : viewMode} onChange={changeView} label="IPAM views" />
    {planning && <ViewTabs items={[...(permissions.write ? [{ id: "allocator", label: "Allocator" }] : []), { id: "resubnet", label: "Resubnet" }]}
      value={viewMode} onChange={onViewModeChange} label="Planning tools" />}
    {viewMode === "import" && <button className="tool-btn tool-btn-ghost" onClick={() => onViewModeChange("search")}>Back to subnets</button>}
    {viewMode === "search" && <div className="ip-search-toolbar"><SubnetSearch subnets={subnets} selectedId={selectedId} tags={tags} selectedTagIds={selectedTagIds}
      onTagFilterChange={onTagFilterChange} onSelect={onSelect} /></div>}
  </div>;
}
