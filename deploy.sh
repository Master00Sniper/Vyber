#!/usr/bin/env bash
# =============================================================================
# deploy.sh — vyber.mortonapps.com — THE ONLY SUPPORTED WAY TO DEPLOY THIS SITE.
#
# Cloudflare Pages builds this site from the GitHub repo (push to `main` =
# build). A raw `git push` is NOT a valid deploy: it skips the cache-buster
# stamp below, so a CSS/JS change can be invisible to returning visitors for
# up to ~4 hours. ALWAYS deploy by running ./deploy.sh.
#
#   1. Stamps a fresh ?v=<UTC-timestamp> onto EVERY local css/js reference
#      across every .html page under web/ (strips any prior ?v first).
#   2. Commits + pushes to origin/main → triggers the CF Pages build.
#
# This repo also holds the desktop app source, so the commit may include app
# changes. Only web/ is published by Pages.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="web"
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

git add -A
if git diff --cached --quiet; then echo "No changes to deploy."; exit 0; fi
git commit -q -m "deploy: stamp assets ?v=${V}"
git pull --rebase --autostash origin main >/dev/null 2>&1 || true
git push origin main
echo "✓ vyber.mortonapps.com deploy pushed (assets ?v=${V}) — Cloudflare Pages is building."
