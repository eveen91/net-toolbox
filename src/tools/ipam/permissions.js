export function canIpam(user, permission) {
  if (!user) return true;
  const permissions = user.permissions || [];
  return permissions.includes("*") || permissions.includes("ipam") || permissions.includes(permission);
}
