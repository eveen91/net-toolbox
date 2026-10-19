export function canDocument(user,action){return !user||(user.permissions||[]).some(value=>value==='*'||value==='documentation'||value===`documentation.${action}`);}
export function canSource(user,permission){return !user||(user.permissions||[]).some(value=>value==='*'||value===permission||(permission==='ipam.read'&&value==='ipam'));}
