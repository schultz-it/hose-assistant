// Relative URLs only: the SPA lives under HA Ingress's proxied path.
async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.status === 204 ? null : resp.json();
}

export const get = (p) => api(p);
export const post = (p, body) =>
  api(p, { method: "POST", body: body && JSON.stringify(body) });
export const put = (p, body) =>
  api(p, { method: "PUT", body: JSON.stringify(body) });
export const del = (p) => api(p, { method: "DELETE" });
