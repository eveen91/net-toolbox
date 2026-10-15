import { buildSubnetTree } from './logic.js';

// Keep matching subnets' ancestors visible as context; search opens their path.
export function subnetBrowserRows(subnets, matchingIds, collapsedIds = new Set(), filtering = false) {
  const matches = new Set(matchingIds);
  const allowed = new Set(matches);
  const byId = new Map(subnets.map(subnet => [subnet.id, subnet]));
  for (const id of matches) {
    let current = byId.get(id);
    const visited = new Set();
    while (current?.parentId != null && byId.has(current.parentId) && !visited.has(current.parentId)) {
      visited.add(current.parentId);
      allowed.add(current.parentId);
      current = byId.get(current.parentId);
    }
  }
  const rows = [];
  const visit = (node, depth) => {
    if (!allowed.has(node.id)) return;
    const children = node.children.filter(child => allowed.has(child.id));
    const expanded = filtering || !collapsedIds.has(node.id);
    rows.push({ subnet: node, depth, isContext: !matches.has(node.id), hasChildren: children.length > 0, expanded });
    if (expanded) children.forEach(child => visit(child, depth + 1));
  };
  buildSubnetTree(subnets).forEach(root => visit(root, 0));
  return rows;
}
