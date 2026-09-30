/**
 * vyber.mortonapps.com as a Worker with static assets (business Cloudflare account).
 *
 * Replaces the personal account's Pages project `vyber` (mortonapps.com zone move,
 * 2026-09-29). The site in ../web is served by the assets layer; this Worker only
 * puts back the Pages behaviour Workers static assets does not have (measured
 * live 2026-09-29 on mortonapps.com, same Pages defaults here):
 *   - clean-URL redirects (/policies.html, /stats/) as 308, not 307;
 *   - charset on text/html, text/css, text/plain; application/javascript for .js;
 *   - Cache-Control: no-store on 404s;
 *   - Access-Control-Allow-Origin: * and Referrer-Policy on every response.
 * The old functions/_middleware.js (301 *.pages.dev to the real host) has no
 * equivalent on purpose: workers_dev and preview_urls are off.
 */
const PAGES_ASSET_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};
const PAGES_CONTENT_TYPES = {
  'text/html': 'text/html; charset=utf-8',
  'text/css': 'text/css; charset=utf-8',
  'text/plain': 'text/plain; charset=utf-8',
  'text/javascript': 'application/javascript',
};

function isCleanUrlRedirect(reqPath, location) {
  if (!location || !location.startsWith('/')) return false;
  const loc = location.split('?')[0];
  const strip = reqPath.replace(/\/index(\.html)?$/, '/').replace(/\.html$/, '');
  return loc === strip || loc === strip.replace(/\/$/, '') || loc === strip + '/'
    || loc === reqPath.replace(/\/$/, '') || loc === reqPath + '/';
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const res = await env.ASSETS.fetch(request);
    let status = res.status;
    const headers = new Headers(res.headers);
    if (status === 307 && isCleanUrlRedirect(url.pathname, headers.get('Location'))) status = 308;
    if (status === 404) headers.set('Cache-Control', 'no-store');
    const ct = (headers.get('Content-Type') || '').toLowerCase();
    if (PAGES_CONTENT_TYPES[ct]) headers.set('Content-Type', PAGES_CONTENT_TYPES[ct]);
    for (const [k, v] of Object.entries(PAGES_ASSET_HEADERS)) if (!headers.has(k)) headers.set(k, v);
    return new Response(res.body, { status, statusText: res.statusText, headers });
  },
};
