import React from "react";
import AddSubnetForm from "./AddSubnetForm.jsx";
import IpamSettingsPopover from "./IpamSettingsPopover.jsx";
import SubnetSearch from "./SubnetSearch.jsx";

export default function IpamToolbar({
  subnets,
  selectedId,
  tags,
  selectedTagIds,
  onTagFilterChange,
  onSelect,
  onCreated,
  viewMode,
  onViewModeChange,
}) {
  return (
    <div className="ip-header-row">
      <SubnetSearch
        subnets={subnets}
        selectedId={selectedId}
        tags={tags}
        selectedTagIds={selectedTagIds}
        onTagFilterChange={onTagFilterChange}
        onSelect={onSelect}
      />
      <AddSubnetForm onCreated={onCreated} />
      <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => onViewModeChange(viewMode === "dashboard" ? "search" : "dashboard")}>
        {viewMode === "dashboard" ? "Back to search" : "Dashboard"}
      </button>
      <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => onViewModeChange(viewMode === "resubnet" ? "search" : "resubnet")}>
        {viewMode === "resubnet" ? "Back to search" : "Resubnet"}
      </button>
      <button className="tool-btn tool-btn-ghost ip-row-btn" onClick={() => onViewModeChange(viewMode === "allocator" ? "search" : "allocator")}>
        {viewMode === "allocator" ? "Back to search" : "Allocator"}
      </button>
      <IpamSettingsPopover />
    </div>
  );
}
