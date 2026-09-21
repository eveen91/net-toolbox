export function togglePageSelection(selectedIds, pageIds) {
  const selected = new Set(selectedIds);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  pageIds.forEach((id) => {
    if (allSelected) selected.delete(id);
    else selected.add(id);
  });
  return [...selected];
}

export function toggleSelection(selectedIds, id) {
  const selected = new Set(selectedIds);
  if (selected.has(id)) selected.delete(id);
  else selected.add(id);
  return [...selected];
}

export function bulkFieldPayload(draft) {
  return Object.fromEntries(Object.entries(draft).filter(([, value]) => value !== ""));
}
