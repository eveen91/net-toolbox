import { useCallback, useEffect, useRef, useState } from "react";
import {
  addAddressTag,
  addSubnetTag,
  deleteSubnet,
  fetchAddressTags,
  fetchSubnetTags,
  fetchTags,
  getSubnet,
  listSubnets,
  removeAddressTag,
  removeSubnetTag,
} from "../api.js";

export function reconcileTagIds(currentTags, nextIds) {
  const currentIds = currentTags.map((tag) => tag.id);
  return {
    toAdd: nextIds.filter((id) => !currentIds.includes(id)),
    toRemove: currentIds.filter((id) => !nextIds.includes(id)),
  };
}

export default function useIpamData() {
  const [subnets, setSubnets] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [highlightedAddressId, setHighlightedAddressId] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [allTags, setAllTags] = useState([]);
  const [tagError, setTagError] = useState(null);
  const [selectedTagIds, setSelectedTagIds] = useState([]);
  const [subnetTagIds, setSubnetTagIds] = useState({});
  const [addressTagIds, setAddressTagIds] = useState({});
  const addressTagCacheRef = useRef(new Set());
  const addressTagRequestsRef = useRef(new Map());
  const selectionGenerationRef = useRef(0);

  const refreshList = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      setSubnets(await listSubnets());
    } catch (error) {
      setListError(error.message);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  useEffect(() => {
    setTagError(null);
    fetchTags()
      .then(setAllTags)
      .catch((error) => setTagError(error.message));
  }, []);

  const loadSubnetTags = useCallback(async (subnetId) => {
    try {
      const tags = await fetchSubnetTags(subnetId);
      setSubnetTagIds((previous) => ({ ...previous, [subnetId]: tags }));
    } catch {
      return;
    }
  }, []);

  const loadAddressTags = useCallback(async (addressId) => {
    if (addressTagCacheRef.current.has(addressId)) return addressTagIds[addressId] || [];
    if (addressTagRequestsRef.current.has(addressId)) {
      return addressTagRequestsRef.current.get(addressId);
    }

    const request = fetchAddressTags(addressId)
      .then((tags) => {
        addressTagCacheRef.current.add(addressId);
        setAddressTagIds((previous) => ({ ...previous, [addressId]: tags }));
        return tags;
      })
      .catch(() => [])
      .finally(() => addressTagRequestsRef.current.delete(addressId));
    addressTagRequestsRef.current.set(addressId, request);
    return request;
  }, [addressTagIds]);

  const handleTagChange = useCallback(async (subnetId, newTagIds) => {
    const { toAdd, toRemove } = reconcileTagIds(subnetTagIds[subnetId] || [], newTagIds);
    for (const tagId of toAdd) await addSubnetTag(subnetId, tagId);
    for (const tagId of toRemove) await removeSubnetTag(subnetId, tagId);
    await loadSubnetTags(subnetId);
  }, [loadSubnetTags, subnetTagIds]);

  const handleAddressTagChange = useCallback(async (addressId, newTagIds) => {
    const { toAdd, toRemove } = reconcileTagIds(addressTagIds[addressId] || [], newTagIds);
    for (const tagId of toAdd) await addAddressTag(addressId, tagId);
    for (const tagId of toRemove) await removeAddressTag(addressId, tagId);
    addressTagCacheRef.current.delete(addressId);
    setAddressTagIds((previous) => {
      const next = { ...previous };
      delete next[addressId];
      return next;
    });
    await loadAddressTags(addressId);
  }, [addressTagIds, loadAddressTags]);

  const handleTagCreated = useCallback((tag) => {
    setAllTags((previous) => previous.some((item) => item.id === tag.id) ? previous : [...previous, tag]);
  }, []);

  const selectSubnet = useCallback(async (id, targetAddressId = null) => {
    const generation = selectionGenerationRef.current + 1;
    selectionGenerationRef.current = generation;
    setSelectedId(id);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    setHighlightedAddressId(targetAddressId || null);
    try {
      const detail = await getSubnet(id);
      if (selectionGenerationRef.current !== generation) return;
      setSelectedDetail(detail);
      setDetailLoading(false);
      void loadSubnetTags(id);
    } catch (error) {
      if (selectionGenerationRef.current !== generation) return;
      setDetailError(error.message);
    } finally {
      if (selectionGenerationRef.current === generation) setDetailLoading(false);
    }
  }, [loadSubnetTags]);

  const handleDetailUpdated = useCallback((detail) => {
    setSelectedDetail(detail);
    refreshList();
  }, [refreshList]);

  const handleDelete = useCallback(async () => {
    if (!selectedId) return;
    setDeleting(true);
    try {
      await deleteSubnet(selectedId);
      setSelectedId(null);
      setSelectedDetail(null);
      await refreshList();
    } catch (error) {
      setDetailError(error.message);
    } finally {
      setDeleting(false);
    }
  }, [refreshList, selectedId]);

  return {
    subnets, listLoading, listError, selectedId, selectedDetail, highlightedAddressId,
    detailLoading, detailError, deleting, allTags, tagError, selectedTagIds,
    subnetTagIds, addressTagIds, setSelectedTagIds, refreshList, selectSubnet,
    handleTagChange, handleAddressTagChange, handleTagCreated, handleDetailUpdated,
    handleDelete, loadAddressTags,
  };
}
