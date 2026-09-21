import React, { useState } from "react";
import "./ipam.css";
import IpamDashboard from "./IpamDashboard.jsx";
import IpamToolbar from "./IpamToolbar.jsx";
import ResubnetReview from "./ResubnetReview.jsx";
import SubnetAllocator from "./SubnetAllocator.jsx";
import SubnetDetail from "./SubnetDetail.jsx";
import TagFilterBar from "./TagFilterBar.jsx";
import useIpamData from "./hooks/useIpamData.js";

export default function Ipam() {
  const [viewMode, setViewMode] = useState("search");
  const {
    subnets, listLoading, listError, selectedId, selectedDetail, highlightedAddressId,
    detailLoading, detailError, deleting, allTags, tagError, selectedTagIds,
    subnetTagIds, addressTagIds, setSelectedTagIds, refreshList, selectSubnet,
    handleTagChange, handleAddressTagChange, handleTagCreated, handleDetailUpdated,
    handleDelete, loadAddressTags,
  } = useIpamData();

  const selectFromSearch = (id, addressId) => {
    setViewMode("search");
    selectSubnet(id, addressId);
  };

  return (
    <div>
      <div className="nt-tool-header">
        <h2>IPAM</h2>
        <p>Track subnets with a VLAN tag, then record individual IP addresses as used, free, or reserved.</p>
      </div>

      <div className="tool-panel">
        <IpamToolbar
          subnets={subnets}
          selectedId={selectedId}
          tags={allTags}
          selectedTagIds={selectedTagIds}
          onTagFilterChange={setSelectedTagIds}
          onSelect={selectFromSearch}
          onCreated={async (created) => {
            await refreshList();
            await selectSubnet(created.id);
          }}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
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
            {!selectedId && !listError && (
              <div className="tool-empty">
                {listLoading
                  ? "Loading subnets…"
                  : subnets.length === 0
                  ? "No subnets yet — add one above to get started."
                  : "Search above to jump to a subnet by CIDR."}
              </div>
            )}
            {selectedId && detailLoading && <div className="tool-empty">Loading…</div>}
            {selectedId && !detailLoading && detailError && <div className="tool-error">{detailError}</div>}
            {selectedId && !detailLoading && selectedDetail && (
              <SubnetDetail
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
                onSelectSubnet={selectSubnet}
                onAddressSelected={loadAddressTags}
                highlightedAddressId={highlightedAddressId}
              />
            )}
          </>
        )}

        {viewMode === "dashboard" && <IpamDashboard onSelectSubnet={selectFromSearch} tags={allTags} />}
        {viewMode === "resubnet" && <ResubnetReview onMoved={refreshList} />}
        {viewMode === "allocator" && (
          <SubnetAllocator
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
