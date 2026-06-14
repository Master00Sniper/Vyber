// Force the canonical custom domain.
//
// The Cloudflare Pages *.pages.dev URL duplicates this site and gets indexed
// separately, splitting traffic and SEO. 301 any *.pages.dev host to the real
// domain. It cannot loop — the canonical host is never a *.pages.dev host — and
// the custom domain passes straight through untouched.
const CANONICAL_HOST = 'vyber.mortonapps.com';

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname.endsWith('.pages.dev')) {
    url.hostname = CANONICAL_HOST;
    url.protocol = 'https:';
    return Response.redirect(url.toString(), 301);
  }
  return context.next();
}
