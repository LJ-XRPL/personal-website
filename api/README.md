# Guestbook API

Small moderated guestbook and visitor counter for lukejudges.com. Python 3 stdlib only (`http.server` + `sqlite3`). One file: `app.py`.

Pending signatures never appear on the site. Luke approves or deletes them from the container. Visitor IPs are not stored: each one is `sha256(LJ_SALT + ip + UTC date)` truncated to 16 hex characters. The IP is taken from `Cf-Connecting-Ip` (what cloudflared passes through).

## What it serves

Routes work with or without an `/api` prefix (`/api/guestbook` and `/guestbook` are the same).

- `GET /health` → `{"ok": true}`
- `GET /visit` → `{"count": n}` (does not increment)
- `POST /visit` → increments once per ip-hash per 30 minutes, unless the user agent looks like a bot (`bot|crawl|spider|slurp|preview|headless`)
- `GET /guestbook` → up to 50 approved entries, newest first
- `POST /guestbook` → stored as pending, `202 {"status":"pending"}`. Links are rejected. A filled honeypot or a form open for under 2.5s gets the same 202 and is stored as nothing. 3 posts per ip-hash per hour, then `429 {"error":"slow down"}`.

Responses are `application/json` with `Cache-Control: no-store`.

## Data

SQLite file at `LJ_DB` (default `/data/lj.db`), on the named volume `guestbook-data`. The volume is the only writable path besides a `/tmp` tmpfs. The server process runs as `nobody` (uid 65534).

Env:

| Name | Default | |
| --- | --- | --- |
| `LJ_DB` | `/data/lj.db` | sqlite file |
| `LJ_PORT` | `8090` | listen port, not published |
| `LJ_SALT` | random each start | set a stable secret or rate limits reset on restart |
| `LJ_COUNT_START` | `0` | seeds the counter the first time the database is created |
| `LJ_DEV_CORS` | unset | `1` sends permissive CORS for a local preview only. Leave unset in production. |

## Admin

Run admin commands as nobody (`-u nobody`) so SQLite's side files stay writable by the server.

From the compose project directory (`~/sites`):

```sh
docker compose exec -u nobody personal-website-api python3 /app/app.py list --pending
docker compose exec -u nobody personal-website-api python3 /app/app.py approve <id>
docker compose exec -u nobody personal-website-api python3 /app/app.py reject <id>
docker compose exec -u nobody personal-website-api python3 /app/app.py count
docker compose exec -u nobody personal-website-api python3 /app/app.py list
```

`list` shows approved entries. `list --pending` is the moderation queue. `reject` deletes the row. Nothing is public until `approve`.

Caddy (see `Caddyfile.proposed`) proxies `/api/*` to `personal-website-api:8090` and forces `Cache-Control: no-store` plus `Cloudflare-CDN-Cache-Control: no-store` on those responses so the site-wide edge cache does not keep guestbook or counter JSON.
