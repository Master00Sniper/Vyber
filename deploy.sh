#!/usr/bin/env bash
# =============================================================================
# deploy.sh — vyber.mortonapps.com — THE ONLY SUPPORTED WAY TO DEPLOY THIS SITE.
#
# The site is the BUSINESS-account Worker `vyber-website` (static assets from
# web/; config in site-worker/). It moved off the personal account's Pages
# project `vyber` with the mortonapps.com zone move (2026-09-29).
#
#   1. Stamps a fresh ?v=<UTC-timestamp> onto EVERY local css/js reference
#      across every .html page under web/ (strips any prior ?v first).
#   2. Commits, rebases on origin/main.
#   3. Deploys the Worker with a PINNED wrangler and the BUSINESS token read BY
#      NAME from ~/.mortoncc-onboarding/credentials. ⛔ Never the ambient
#      CLOUDFLARE_API_TOKEN: ~/.bashrc exports the PERSONAL token into every
#      shell (memory: feedback_cf_account_isolation).
#   4. Pushes to origin/main for source history. Until the zone cutover the
#      push ALSO rebuilds the old personal Pages project (still live then), so
#      both copies stay identical; after the cutover its git builds are
#      switched off and the push is history only.
# A failed deploy stops before the push.
#
# This repo also holds the desktop app source, so the commit may include app
# changes. Only web/ is published. The app's backend (telemetry, stats,
# downloads, issues) is a different Worker, `vyber-proxy`, in cloudflare-worker/
# (deploy command in its wrangler.toml).
# Override the wrangler pin for one run: WRANGLER=wrangler@x.y.z ./deploy.sh
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="web"
WRANGLER="${WRANGLER:-wrangler@4.124.0}"
BIZ_ACCOUNT_ID="2188c49e0e996a3542239668d9fcc8e7"
CRED="$HOME/.mortoncc-onboarding/credentials"
BIZ_TOKEN="$(grep -vE '^\s*#' "$CRED" | grep -oP '^CLOUDFLARE_API_TOKEN=["'\'']?\K[^"'\'' ]+' | head -1 || true)"
[ -n "$BIZ_TOKEN" ] || { echo "✗ no CLOUDFLARE_API_TOKEN line in $CRED (the business token)"; exit 1; }
V="$(date -u +%Y%m%d%H%M%S)"

STAMP_ROOT="$ROOT" STAMP_V="$V" node <<'NODE'
const fs = require('fs'), path = require('path');
const root = process.env.STAMP_ROOT, V = process.env.STAMP_V;
function walk(d){let o=[];for(const e of fs.readdirSync(d,{withFileTypes:true})){const p=path.join(d,e.name);if(e.isDirectory()){if(e.name==='node_modules'||e.name==='.git')continue;o=o.concat(walk(p));}else if(e.name.endsWith('.html'))o.push(p);}return o;}
const re = /(\b(?:href|src)=")((?!https?:\/\/|\/\/)[^"?]+?\.(?:css|js))(?:\?[^"]*)?(")/g;
let n = 0;
for (const f of walk(root)) {
  const s = fs.readFileSync(f, 'utf8');
  const t = s.replace(re, (m, a, p, b) => `${a}${p}?v=${V}${b}`);
  if (t !== s) { fs.writeFileSync(f, t); n++; }
}
console.log('stamped ' + n + ' html file(s) with ?v=' + V);
NODE

git add -A -- "$ROOT"   # stage only the deployed site (MCC sibling fix 2026-10-06; never a bare add-all)
OTHER=$(git status --porcelain | grep -v "^.. $ROOT/" || true)
[ -n "$OTHER" ] && { echo "Not committed (outside $ROOT/, review by hand):"; echo "$OTHER"; }
if git diff --cached --quiet; then
  echo "No source changes; redeploying the current tree."
else
  git commit -q -m "deploy: stamp assets ?v=${V}"
fi
git pull --rebase --autostash origin main >/dev/null 2>&1 || true

( cd site-worker && CLOUDFLARE_API_TOKEN="$BIZ_TOKEN" CLOUDFLARE_ACCOUNT_ID="$BIZ_ACCOUNT_ID" npx -y "$WRANGLER" deploy )

git push origin main
echo "✓ vyber.mortonapps.com deployed to Worker vyber-website (business) and pushed (assets ?v=${V})."
