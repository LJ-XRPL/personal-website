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

## Runner leaderboard

`GET /api/scores` returns the top 10 approved runs, best first. `POST /api/scores` stores a run as pending (`202 {"status":"pending"}`) and never lists it until `approve-score`. Same `Cache-Control: no-store` as the guestbook. Routes work with or without an `/api` prefix.

A score is what the career runner actually measures. The level is 9 role obstacles (x starts at 640, then +560, except +1100 after the 8th) and 5 optional mics. Speed is `300 + 70 * min(1, worldX / 6540)` px/s. Jumps do not change it. The flag is at x 6540. Canvas offset RX is 28 below 520px wide, otherwise 64.

Fields, all integers:

| Field | Meaning | Limit |
| --- | --- | --- |
| `roles` | roles cleared before the run ended | 0–9. A finish is 9. A crash is 0–8 (the role you hit is not cleared). |
| `media` | mics collected (`got`) | 0–5. 1–3 only after 8 roles (mics sit after role 8). 4–5 only on a finish (those mics are past the last role). |
| `done` | 1 finished, 0 crashed | 1 only with `roles` 9. |
| `ms` | game-time milliseconds | inside the physics window for that outcome, across both RX values. Fastest is the rising-speed curve; slowest is one step at 300px/s. 1s of slack covers a 33ms frame. |

Rank: finished above crashed, then more roles, then more mics, then a faster finish (`ms` ascending, finishes only), then earlier id.

`name` is 1–16 printable characters after the same trim and control-character strip as a guestbook name. Links are rejected (`no links please`). Anything else off is `check score` or `check name`.

Rate limit matches the guestbook (3 posts per ip-hash per hour, same salt and `sha256(salt + ip + UTC date)` truncated to 16 hex chars) but uses its own `score_posts` table, so signing the guestbook does not spend the runner quota. No raw IP is stored.

The tables are `CREATE TABLE IF NOT EXISTS`. Starting this build against the existing guestbook database adds `scores` and `score_posts` and does not alter `entries`, `visits`, `posts`, or `meta`.

```sh
docker compose exec -u nobody personal-website-api python3 /app/app.py scores --pending
docker compose exec -u nobody personal-website-api python3 /app/app.py approve-score <id>
docker compose exec -u nobody personal-website-api python3 /app/app.py reject-score <id>
docker compose exec -u nobody personal-website-api python3 /app/app.py scores
```

`scores` is the approved board. `scores --pending` is the queue. `reject-score` deletes the row. The running container only loads a new `app.py` on `docker compose up -d --force-recreate personal-website-api`.

