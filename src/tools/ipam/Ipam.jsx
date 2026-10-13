import React, { useState } from "react";
import "./ipam.css";
import ArchiveReview from "./ArchiveReview.jsx";
import DataQualityReview from "./DataQualityReview.jsx";
import IpamImport from "./IpamImport.jsx";
import IpamDashboard from "./IpamDashboard.jsx";
import IpamToolbar from "./IpamToolbar.jsx";
import ResubnetReview from "./ResubnetReview.jsx";
import SubnetAllocator from "./SubnetAllocator.jsx";
import SubnetDetail from "./SubnetDetail.jsx";
import TagFilterBar from "./TagFilterBar.jsx";
import useIpamData from "./hooks/useIpamData.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { canIpam } from "./permissions.js";
import SubnetBrowser from "./SubnetBrowser.jsx";
import { canLeaveWorkspace } from "../../components/navigation.js";

export default function Ipam() {
  const { user } = useAuth();
  const permissions = { read: canIpam(user, "ipam.read"), write: canIpam(user, "ipam.write"), scan: canIpam(user, "ipam.scan"), admin: canIpam(user, "ipam.admin") };
  const [moveNotice, setMoveNotice] = useState(null);
  const [viewMode, setViewMode] = useState("search");
  const {
    subnets, listLoading, listError, selectedId, selectedDetail, highlightedAddressId,
    detailLoading, detailError, deleting, allTags, tagError, selectedTagIds,
    subnetTagIds, addressTagIds, setSelectedTagIds, refreshList, selectSubnet,
    handleTagChange, handleAddressTagChange, handleTagCreated, handleDetailUpdated,
    handleDelete, loadAddressTags, clearSelection,
  } = useIpamData();

  const selectFromSearch = (id, addressId) => {
    if (!canLeaveWorkspace()) return;
    setViewMode("search");
    selectSubnet(id, addressId);
  };

  return (
    <div className="ip-workspace">
      <div className="nt-tool-header">
        <h2>IPAM</h2>
        <p>Track subnets with a VLAN tag, then record individual IP addresses as used, free, or reserved.</p>
      </div>

      <div className="tool-panel">
        {moveNotice && <p role="status">{moveNotice}</p>}
        <IpamToolbar
          subnets={subnets}
          selectedId={selectedId}
          tags={allTags}
          selectedTagIds={selectedTagIds}
          onTagFilterChange={setSelectedTagIds}
          onSelect={selectFromSearch}
          onCreated={async (created) => {
            setViewMode("search");
            await refreshList();
            await selectSubnet(created.id);
          }}
          viewMode={viewMode}
          onViewModeChange={(mode) => { if (canLeaveWorkspace()) setViewMode(mode); }}
          permissions={permissions}
        />

        {selectedTagIds.length > 0 && (
          <TagFilterBar
            tags={allTags.filter((tag) => selectedTagIds.includes(tag.id))}
            onRemove={(tagId) => setSelectedTagIds((previous) => previous.filter((id) => id !== tagId))}
          />
        )}

        {viewMode === "search" && (
          <>
            {listError && <div className="tool-error">{listError}</div>}
            {tagError && <div className="tool-error">Unable to load tags: {tagError}</div>}
            <div className="ip-divider" />
            {!selectedId && !listError && <SubnetBrowser subnets={subnets} selectedTagIds={selectedTagIds} onSelect={selectFromSearch} loading={listLoading} />}
            {selectedId && <button className="tool-btn tool-btn-ghost ip-browse-back" onClick={() => { if (canLeaveWorkspace()) clearSelection(); }}>Browse all subnets</button>}
            {selectedId && detailLoading && <div className="tool-empty">Loading…</div>}
            {selectedId && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}
            {selectedId && !detailLoading && selectedDetail && (
              <SubnetDetail
                onMoved={result => {
                  clearSelection();
                  setMoveNotice(`Moved ${result.cidr} to ${result.targetTenantName}.`);
                  refreshList();
                }}
                subnet={selectedDetail}
                subnets={subnets}
                tags={allTags}
                subnetTagIds={subnetTagIds[selectedId] || []}
                onTagChange={(newIds) => handleTagChange(selectedId, newIds)}
                onTagCreated={handleTagCreated}
                addressTagIds={addressTagIds}
                onAddressTagChange={handleAddressTagChange}
                deleting={deleting}
                onDelete={handleDelete}
                onDetailUpdated={handleDetailUpdated}
                onSelectSubnet={selectFromSearch}
                onAddressSelected={loadAddressTags}
                highlightedAddressId={highlightedAddressId}
                permissions={permissions}
                canWrite={permissions.write}
                canScan={permissions.scan}
              />
            )}
          </>
        )}

        {viewMode === "dashboard" && <IpamDashboard onSelectSubnet={selectFromSearch} tags={allTags} />}
        {viewMode === "import" && permissions.write && <IpamImport onImported={refreshList} />}
        {viewMode === "archive" && <ArchiveReview canWrite={permissions.write} onRestored={refreshList} />}
        {viewMode === "quality" && <DataQualityReview onSelectSubnet={selectFromSearch} onChanged={refreshList} canWrite={permissions.write} />}
        {viewMode === "resubnet" && <ResubnetReview onMoved={refreshList} canWrite={permissions.write} />}
        {viewMode === "allocator" && permissions.write && (
          <SubnetAllocator
            canAdmin={permissions.admin}
            subnets={subnets}
            tags={allTags}
            onTagCreated={handleTagCreated}
            onCreate={(created) => {
              refreshList();
              setViewMode("search");
              setTimeout(() => selectSubnet(created.id), 50);
            }}
          />
        )}
      </div>
    </div>
  );
}
