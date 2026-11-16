#!/usr/bin/env python3
"""Moderated guestbook and visitor counter for lukejudges.com.

Stdlib only. No raw IPs are stored: each visitor is sha256(salt + ip + UTC
date), truncated. Pending entries are invisible until `approve`.

  python3 app.py serve
  python3 app.py list [--pending]
  python3 app.py approve <id>
  python3 app.py reject <id>
  python3 app.py count
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 2048
VISIT_WINDOW = 30 * 60
POST_WINDOW = 60 * 60
POST_LIMIT = 3
HASH_LEN = 16
ROUTES = ("visit", "guestbook", "health")

BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|headless", re.I)
LINK_RE = re.compile(r"http|www\.|\.[a-z]{2,24}/", re.I)

_lock = threading.Lock()


def env_db():
    return os.environ.get("LJ_DB", "/data/lj.db")


def env_port():
    return int(os.environ.get("LJ_PORT", "8090"))


def env_salt():
    salt = os.environ.get("LJ_SALT")
    if not salt:
        salt = os.urandom(16).hex()
        os.environ["LJ_SALT"] = salt
    return salt


def env_count_start():
    return int(os.environ.get("LJ_COUNT_START", "0"))


def dev_cors():
    return os.environ.get("LJ_DEV_CORS") == "1"


def connect():
    path = env_db()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db():
    with _lock:
        conn = connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visits (
                    iphash TEXT PRIMARY KEY,
                    seen INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    msg TEXT NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    iphash TEXT NOT NULL,
                    created INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    iphash TEXT NOT NULL,
                    created INTEGER NOT NULL
                );
                """
            )
            row = conn.execute("SELECT v FROM meta WHERE k = 'count'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta (k, v) VALUES ('count', ?)",
                    (str(env_count_start()),),
                )
            conn.commit()
        finally:
            conn.close()


def utc_day(ts=None):
    moment = datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc)
    return moment.strftime("%Y-%m-%d")


def ip_hash(ip, day=None):
    raw = (env_salt() + ip + (day or utc_day())).encode()
    return hashlib.sha256(raw).hexdigest()[:HASH_LEN]


def client_ip(handler):
    forwarded = handler.headers.get("Cf-Connecting-Ip") or ""
    ip = forwarded.split(",")[0].strip()
    if not ip:
        ip = handler.client_address[0] or ""
    return ip


def is_bot(handler):
    return bool(BOT_RE.search(handler.headers.get("User-Agent") or ""))


def strip_ctrl(text):
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cc")


def has_link(text):
    return bool(LINK_RE.search(text))


def get_count(conn):
    row = conn.execute("SELECT v FROM meta WHERE k = 'count'").fetchone()
    return int(row["v"]) if row else 0


def trail(path):
    path = path.split("?", 1)[0]
    parts = [part for part in path.split("/") if part]
    if parts and parts[-1] in ROUTES:
        return "/" + parts[-1]
    return "/"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Path only. Never log Cf-Connecting-Ip or a body.
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?", 1)[0]))

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        if dev_cors() and trail(self.path) in ("/visit", "/guestbook", "/health"):
            self._send(204, b"")
            return
        self._send_json(405, {"error": "method"})

    def do_PUT(self):
        self._send_json(405, {"error": "method"})

    def do_DELETE(self):
        self._send_json(405, {"error": "method"})

    def do_PATCH(self):
        self._send_json(405, {"error": "method"})

    def _dispatch(self, method):
        try:
            route = trail(self.path)
            if route == "/health":
                if method != "GET":
                    self._send_json(405, {"error": "method"})
                    return
                self._send_json(200, {"ok": True})
                return
            if route == "/visit":
                if method == "GET":
                    self._visit(increment=False)
                elif method == "POST":
                    self._visit(increment=True)
                else:
                    self._send_json(405, {"error": "method"})
                return
            if route == "/guestbook":
                if method == "GET":
                    self._list_entries()
                elif method == "POST":
                    self._sign()
                else:
                    self._send_json(405, {"error": "method"})
                return
            self._send_json(404, {"error": "not found"})
        except Exception:
            self._send_json(500, {"error": "error"})

    def _visit(self, increment):
        with _lock:
            conn = connect()
            try:
                if increment and not is_bot(self):
                    now = int(time.time())
                    hashed = ip_hash(client_ip(self))
                    row = conn.execute(
                        "SELECT seen FROM visits WHERE iphash = ?", (hashed,)
                    ).fetchone()
                    if row is None or now - int(row["seen"]) >= VISIT_WINDOW:
                        conn.execute(
                            "INSERT INTO visits (iphash, seen) VALUES (?, ?) "
                            "ON CONFLICT(iphash) DO UPDATE SET seen = excluded.seen",
                            (hashed, now),
                        )
                        conn.execute(
                            "UPDATE meta SET v = CAST(CAST(v AS INTEGER) + 1 AS TEXT) WHERE k = 'count'"
                        )
                        conn.commit()
                count = get_count(conn)
            finally:
                conn.close()
        self._send_json(200, {"count": count})

    def _list_entries(self):
        with _lock:
            conn = connect()
            try:
                rows = conn.execute(
                    "SELECT id, name, msg, date FROM entries "
                    "WHERE status = 'approved' ORDER BY id DESC LIMIT 50"
                ).fetchall()
            finally:
                conn.close()
        entries = [
            {"id": row["id"], "name": row["name"], "msg": row["msg"], "date": row["date"]}
            for row in rows
        ]
        self._send_json(200, {"entries": entries})

    def _read_json(self):
        ctype = self.headers.get("Content-Type") or ""
        if ctype.split(";", 1)[0].strip().lower() != "application/json":
            self._send_json(400, {"error": "json only"})
            return None
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._send_json(400, {"error": "bad request"})
            return None
        if length < 0 or length > MAX_BODY:
            self._send_json(413, {"error": "too large"})
            return None
        raw = self.rfile.read(length) if length else b""
        if len(raw) > MAX_BODY:
            self._send_json(413, {"error": "too large"})
            return None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "bad json"})
            return None
        if not isinstance(data, dict):
            self._send_json(400, {"error": "bad json"})
            return None
        return data

    def _sign(self):
        data = self._read_json()
        if data is None:
            return
        name = data.get("name")
        msg = data.get("msg")
        if not isinstance(name, str) or not isinstance(msg, str):
            self._send_json(400, {"error": "check name and message"})
            return
        name = strip_ctrl(name).strip()
        msg = strip_ctrl(msg).strip()
        if not (1 <= len(name) <= 32) or not (1 <= len(msg) <= 140):
            self._send_json(400, {"error": "check name and message"})
            return
        if has_link(name) or has_link(msg):
            self._send_json(400, {"error": "no links please"})
            return
        if _silent_drop(data):
            self._send_json(202, {"status": "pending"})
            return
        now = int(time.time())
        hashed = ip_hash(client_ip(self))
        with _lock:
            conn = connect()
            try:
                recent = conn.execute(
                    "SELECT COUNT(*) AS n FROM posts WHERE iphash = ? AND created >= ?",
                    (hashed, now - POST_WINDOW),
                ).fetchone()["n"]
                if recent >= POST_LIMIT:
                    self._send_json(429, {"error": "slow down"})
                    return
                conn.execute(
                    "INSERT INTO entries (name, msg, date, status, iphash, created) "
                    "VALUES (?, ?, ?, 'pending', ?, ?)",
                    (name, msg, utc_day(now), hashed, now),
                )
                conn.execute(
                    "INSERT INTO posts (iphash, created) VALUES (?, ?)",
                    (hashed, now),
                )
                conn.commit()
            finally:
                conn.close()
        self._send_json(202, {"status": "pending"})

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _send(self, code, body, content_type=None):
        self.send_response(code)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if dev_cors():
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if body:
            self.wfile.write(body)


def _silent_drop(data):
    hp = data.get("hp", "")
    if hp is None:
        hp = ""
    if isinstance(hp, str):
        if hp != "":
            return True
    elif hp:
        return True
    t = data.get("t", None)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or t < 2500:
        return True
    return False


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def make_server(host="127.0.0.1", port=0):
    init_db()
    return Server((host, port), Handler)


def serve():
    init_db()
    httpd = Server(("0.0.0.0", env_port()), Handler)
    httpd.serve_forever()


def _print_rows(rows):
    for row in rows:
        print(f"{row['id']}\t{row['status']}\t{row['date']}\t{row['name']}\t{row['msg']}")


def cmd_list(pending):
    init_db()
    conn = connect()
    try:
        if pending:
            rows = conn.execute(
                "SELECT id, status, date, name, msg FROM entries "
                "WHERE status = 'pending' ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, status, date, name, msg FROM entries "
                "WHERE status = 'approved' ORDER BY id"
            ).fetchall()
    finally:
        conn.close()
    _print_rows(rows)
    return 0


def cmd_approve(entry_id):
    init_db()
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE entries SET status = 'approved' WHERE id = ?", (entry_id,)
        )
        conn.commit()
        found = cur.rowcount > 0
    finally:
        conn.close()
    print("approved" if found else "not found")
    return 0 if found else 1


def cmd_reject(entry_id):
    init_db()
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        found = cur.rowcount > 0
    finally:
        conn.close()
    print("rejected" if found else "not found")
    return 0 if found else 1


def cmd_count():
    init_db()
    conn = connect()
    try:
        print(get_count(conn))
    finally:
        conn.close()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ["serve"]:
        serve()
        return 0
    if argv == ["list"]:
        return cmd_list(False)
    if argv == ["list", "--pending"]:
        return cmd_list(True)
    if len(argv) == 2 and argv[0] == "approve" and argv[1].isdigit():
        return cmd_approve(int(argv[1]))
    if len(argv) == 2 and argv[0] == "reject" and argv[1].isdigit():
        return cmd_reject(int(argv[1]))
    if argv == ["count"]:
        return cmd_count()
    print(
        "usage: app.py serve | list [--pending] | approve <id> | reject <id> | count",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
