let token = '';
export function setToken(value: string) {
  token = value;
}
export async function request(path: string, options: RequestInit = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return response;
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await request(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.json();
}
export async function upload(file: File, batch: string) {
  const body = new FormData();
  body.append('file', file);
  body.append('batch', batch);
  return (await request('/inspections', { method: 'POST', body })).json();
}
export async function imageUrl(id: string, heatmap = false, signal?: AbortSignal) {
  const response = await request(`/inspections/${id}/image${heatmap ? '?kind=heatmap' : ''}`, {
    signal,
  });
  return URL.createObjectURL(await response.blob());
}
export async function download() {
  const response = await request('/export');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = 'visionguard-inspections.csv';
  link.click();
  URL.revokeObjectURL(url);
}
