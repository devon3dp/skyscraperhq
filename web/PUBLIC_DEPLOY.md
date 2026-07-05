# Public Deployment — Tower Studio + Lumen AI

Both sites currently run on `127.0.0.1` (local-only). Going public is a
separate Claude phase that flips two gates and adds hosting credentials.
Here is the exact spec.

## What's already done

Static assets are real files on disk:

  web/tower_studio/index.html        — landing page
  web/tower_studio/static/*.css/js   — site styling + JS
  web/tower_studio/static/hero.svg   — generated hero illustration
  web/tower_studio/portfolio/*.svg   — generated portfolio concepts

  web/lumen_ai/index.html            — landing + chat playground
  web/lumen_ai/static/*.css/js       — site styling + chat JS

For Tower Studio, the static directory CAN be served by any static host
(GitHub Pages / Netlify / Vercel / Cloudflare Pages). The contact form
+ services + customers APIs need a small backend.

For Lumen AI, the chat playground can be served statically; the chat
backend needs a Python host because it routes through the Kernel.

## Recommended hosting (free tier)

  TIER 1 — STATIC ONLY (Tower Studio landing pages):
    - GitHub Pages           (commit web/tower_studio/ to a branch)
    - Netlify Drop           (drag-and-drop the folder)
    - Cloudflare Pages       (point at a GitHub repo)

  TIER 2 — STATIC + SMALL BACKEND (full Tower Studio + Lumen):
    - Fly.io                  (Docker; free 256MB VM; Python OK)
    - Railway                 (Python + persistent storage)
    - Render                  (free Python web service; sleeps after idle)
    - PythonAnywhere          (free Python web app; manual restart)

Both Tower Studio and Lumen AI fit in 256MB easily.

## Required env variables for the public phase

  TOWER STUDIO
    QSB_STUDIO_REGISTRY_DIR       path where the production registries write
    QSB_STUDIO_ALLOWED_ORIGINS    comma-separated list for CORS
    QSB_STUDIO_RATE_LIMIT_RPM     requests per minute per IP
    QSB_STUDIO_CONTACT_NOTIFY_TO  email to forward leads to (optional)

  LUMEN AI
    QSB_LUMEN_REGISTRY_DIR        path where conversations persist
    QSB_LUMEN_ALLOWED_ORIGINS     CORS allowlist
    QSB_LUMEN_RATE_LIMIT_RPM      per-IP rate limit
    QSB_LUMEN_REQUIRE_API_KEY     true/false — gate the playground

Both sites should sit behind a reverse proxy (Caddy or nginx) that
provides TLS via Let's Encrypt. Direct exposure of Python's
http.server is not advised for the public internet — but for one
operator's playground behind a tunnel (Cloudflare Tunnel /
Tailscale Funnel), it is fine.

## Gates that flip at deploy time

The Kernel will refuse to enter "public" mode unless these are flipped:

  FLAGS["public_website_published"]         True      (Tower Studio)
  FLAGS["public_api_open"]                  True      (Lumen)
  FLAGS["real_payments_enabled"]            True      (only after Square wiring)
  FLAGS["external_api_calls_enabled"]       True      (only if needed)

Each flip is a SEPARATE operator decision. The Kernel will not flip
them itself.

## One-shot deploy commands (when the operator is ready)

  # GitHub Pages (Tower Studio landing, static only):
  cd web/tower_studio
  git init && git remote add origin git@github.com:OWNER/REPO.git
  git add . && git commit -m "tower studio launch"
  git push -u origin main:gh-pages

  # Cloudflare Tunnel (Lumen, behind your existing tunnel):
  cloudflared tunnel route dns YOUR-TUNNEL lumen.yourdomain.com
  cloudflared tunnel run --url http://127.0.0.1:8848 YOUR-TUNNEL

  # Fly.io (Python backend + frontend, recommended for Lumen):
  fly launch --no-deploy
  fly secrets set QSB_LUMEN_RATE_LIMIT_RPM=60
  fly deploy

## What the future Claude phase must do (specification)

  1. Read web/PUBLIC_DEPLOY.md (this file).
  2. Confirm with the operator which provider + which gate to flip first.
  3. Write a Dockerfile / fly.toml / netlify.toml as appropriate.
  4. Add CORS + rate limiting + API-key gating to the Python servers.
  5. Flip ONLY the gates the operator has authorised in that session.
  6. Run a smoke test against the deployed URL.
  7. Document the deploy in the repo.

The Kernel never auto-deploys. It only proposes.
