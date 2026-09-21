export function prefixBounds(parentCidr) {
  const prefix = Number(parentCidr?.split("/")[1]);
  return Number.isInteger(prefix) ? { min: prefix, max: 32 } : { min: 0, max: 32 };
}

export function allocationDraftToRequest({ parent, cidr, freshnessToken, vlan, description, tagIds }) {
  return {
    parent,
    cidr,
    freshnessToken,
    vlan: vlan === "" || vlan == null ? null : Number(vlan),
    description: description?.trim() || null,
    tagIds,
  };
}
