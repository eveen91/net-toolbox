import { apiFetch } from '../../apiFetch.js';

const ROOT = '/api/dhcp-generator/configurations';
async function request(path = '', method = 'GET', body) {
  const response = await apiFetch(ROOT + path, { method, ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { /* Retain HTTP context. */ }
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('\n') : detail?.message;
    const error = new Error(message || `DHCP request failed (${response.status})`);
    error.status = response.status;
    error.code = detail?.code;
    error.report = detail?.report;
    throw error;
  }
  return response.json();
}
const idPath = id => `/${encodeURIComponent(id)}`;
export const listConfigurations = (query = '', offset = 0) => request(`?${new URLSearchParams({ query, offset, limit: 20 })}`);
export const getConfiguration = id => request(idPath(id));
export const createConfiguration = configuration => request('', 'POST', { configuration });
export const saveConfiguration = (id, expectedRevision, configuration) => request(idPath(id), 'PUT', { expectedRevision, configuration });
export const previewConfiguration = (id, expectedRevision) => request(`${idPath(id)}/preview`, 'POST', { expectedRevision });
export const publishVersion = (id, expectedRevision, description) => request(`${idPath(id)}/versions`, 'POST', { expectedRevision, description });
export const listVersions = (id, offset = 0) => request(`${idPath(id)}/versions?${new URLSearchParams({ offset, limit: 20 })}`);
export const getVersion = (id, versionId) => request(`${idPath(id)}/versions/${encodeURIComponent(versionId)}`);
export const restoreVersion = (id, expectedRevision, versionId) => request(`${idPath(id)}/restore`, 'POST', { expectedRevision, versionId });
export const compareVersions = (id, before, after) => request(`${idPath(id)}/diff?${new URLSearchParams({ before, after })}`);
export const getAudit = (id, offset = 0) => request(`${idPath(id)}/audit?${new URLSearchParams({ offset, limit: 20 })}`);

export async function downloadArtifact(id, version) {
  const response = await apiFetch(`${ROOT}${idPath(id)}/versions/${encodeURIComponent(version.id)}/artifact`);
  if (!response.ok) throw new Error(`Artifact download failed (${response.status})`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `dhcp-v${version.number}-dhcpd.conf`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
