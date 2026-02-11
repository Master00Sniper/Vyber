addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

// Known routes — reject everything else early
const KNOWN_ROUTES = ['/download/latest', '/telemetry', '/stats'];
const ALLOWED_REPO_PREFIX = '/repos/Master00Sniper/Vyber/';

// Rate limit: max requests per IP for the public download endpoint
const DOWNLOAD_RATE_LIMIT = 30;   // requests per window
const DOWNLOAD_RATE_WINDOW = 3600; // 1 hour in seconds

// Cache TTL for /download/latest (avoids burning GitHub API calls)
const DOWNLOAD_CACHE_TTL = 600; // 10 minutes

async function handleRequest(request) {
  const url = new URL(request.url);

  // Handle CORS preflight requests
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, HEAD, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Accept, User-Agent, X-Vyber-Auth',
        'Access-Control-Max-Age': '86400'
      }
    });
  }

  // =========================================
  // Early rejection — unknown routes get 404
  // =========================================
  const isKnownRoute = KNOWN_ROUTES.includes(url.pathname);
  const isRepoProxy = url.pathname.startsWith(ALLOWED_REPO_PREFIX);
  if (!isKnownRoute && !isRepoProxy) {
    return new Response('Not Found', { status: 404 });
  }

  // =========================================
  // Download latest release (PUBLIC - no auth)
  // Cached + rate-limited to protect GitHub PAT
  // =========================================
  if (url.pathname === '/download/latest') {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // --- Per-IP rate limiting via KV ---
    const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
    const rateLimitKey = `ratelimit:download:${clientIP}`;
    const hitCount = parseInt(await VYBER_TELEMETRY.get(rateLimitKey) || '0');
    if (hitCount >= DOWNLOAD_RATE_LIMIT) {
      return new Response('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': '3600' }
      });
    }
    await VYBER_TELEMETRY.put(rateLimitKey, (hitCount + 1).toString(), {
      expirationTtl: DOWNLOAD_RATE_WINDOW
    });

    // --- Check Cloudflare Cache first ---
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    let cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) {
      return cachedResponse;
    }

    try {
      const releaseResponse = await fetch(
        'https://api.github.com/repos/Master00Sniper/Vyber/releases/latest',
        {
          headers: {
            'Authorization': `token ${GITHUB_PAT}`,
            'User-Agent': 'Vyber-Proxy/1.0',
            'Accept': 'application/vnd.github.v3+json'
          }
        }
      );

      if (!releaseResponse.ok) {
        return new Response('Failed to fetch release info', { status: 500 });
      }

      const release = await releaseResponse.json();

      // Find the .exe asset
      const asset = release.assets.find(a =>
        a.name.includes('Vyber') && a.name.endsWith('.exe')
      );

      if (!asset) {
        return new Response('No download found', { status: 404 });
      }

      // Build a cacheable redirect response
      const redirectResponse = new Response(null, {
        status: 302,
        headers: {
          'Location': asset.browser_download_url,
          'Cache-Control': `public, max-age=${DOWNLOAD_CACHE_TTL}`,
          'Access-Control-Allow-Origin': '*'
        }
      });

      // Store in Cloudflare edge cache
      await cache.put(cacheKey, redirectResponse.clone());

      return redirectResponse;
    } catch (e) {
      return new Response('Error fetching download', { status: 500 });
    }
  }

  // =========================================
  // Auth required for all endpoints below
  // =========================================
  const authHeader = request.headers.get('X-Vyber-Auth');
  if (!authHeader || authHeader !== VYBER_AUTH_KEY) {
    return new Response('Unauthorized', { status: 401 });
  }

  // =========================================
  // Telemetry endpoint
  // =========================================
  if (url.pathname === '/telemetry' && request.method === 'POST') {
    try {
      const data = await request.json();
      const { event, version, os, install_id } = data;

      if (!event || !install_id) {
        return new Response('Missing required fields', { status: 400 });
      }

      // Use Pacific time instead of UTC
      const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' });

      // Track daily active users (unique install_ids per day)
      const dauKey = `dau:${today}`;
      const existingDAU = await VYBER_TELEMETRY.get(dauKey, { type: 'json' }) || [];
      if (!existingDAU.includes(install_id)) {
        existingDAU.push(install_id);
        await VYBER_TELEMETRY.put(dauKey, JSON.stringify(existingDAU), {
          expirationTtl: 60 * 60 * 24 * 90 // Keep for 90 days
        });
      }

      // Track total events per day (only low-frequency events to conserve KV ops)
      if (event === 'app_start' || event === 'heartbeat') {
        const eventKey = `events:${today}:${event}`;
        const eventCount = parseInt(await VYBER_TELEMETRY.get(eventKey) || '0') + 1;
        await VYBER_TELEMETRY.put(eventKey, eventCount.toString(), {
          expirationTtl: 60 * 60 * 24 * 90
        });
      }

      // Track version distribution (only on app_start — version doesn't change mid-session)
      if (version && event === 'app_start') {
        const versionKey = `version:${today}:${version}`;
        const versionCount = parseInt(await VYBER_TELEMETRY.get(versionKey) || '0') + 1;
        await VYBER_TELEMETRY.put(versionKey, versionCount.toString(), {
          expirationTtl: 60 * 60 * 24 * 90
        });
      }

      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        }
      });
    } catch (e) {
      return new Response('Error processing telemetry', { status: 500 });
    }
  }

  // =========================================
  // Stats endpoint (check your usage)
  // =========================================
  if (url.pathname === '/stats') {
    try {
      // Use Pacific time instead of UTC
      const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' });
      const dau = await VYBER_TELEMETRY.get(`dau:${today}`, { type: 'json' }) || [];
      const starts = await VYBER_TELEMETRY.get(`events:${today}:app_start`) || '0';
      const heartbeats = await VYBER_TELEMETRY.get(`events:${today}:heartbeat`) || '0';

      return new Response(JSON.stringify({
        date: today,
        daily_active_users: dau.length,
        app_starts: parseInt(starts),
        heartbeats: parseInt(heartbeats)
      }, null, 2), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        }
      });
    } catch (e) {
      return new Response('Error fetching stats', { status: 500 });
    }
  }

  // =========================================
  // GitHub API Proxy — restricted to Vyber repo
  // =========================================
  const githubUrl = `https://api.github.com${url.pathname}${url.search}`;

  // Build headers for GitHub request
  const githubHeaders = new Headers();
  githubHeaders.set('Authorization', `token ${GITHUB_PAT}`);
  githubHeaders.set('User-Agent', request.headers.get('User-Agent') || 'Vyber-Updater/1.0');
  githubHeaders.set('Accept', request.headers.get('Accept') || 'application/vnd.github.v3+json');

  // Add Content-Type for POST requests
  if (request.method === 'POST') {
    githubHeaders.set('Content-Type', 'application/json');
  }

  // Fetch from GitHub (include body for POST requests)
  try {
    const fetchOptions = {
      method: request.method,
      headers: githubHeaders
    };

    // Forward request body for POST/PUT/PATCH
    if (['POST', 'PUT', 'PATCH'].includes(request.method)) {
      fetchOptions.body = await request.text();
    }

    const response = await fetch(githubUrl, fetchOptions);

    // Return response with CORS headers
    const newResponse = new Response(response.body, response);
    newResponse.headers.set('Access-Control-Allow-Origin', '*');
    newResponse.headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS');

    return newResponse;
  } catch (error) {
    return new Response(`Proxy error: ${error.message}`, { status: 500 });
  }
}
