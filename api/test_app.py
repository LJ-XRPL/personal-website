#!/usr/bin/env python3
"""Integration tests for the guestbook API. Starts the server on a random port."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="lj-guest-")
DB = os.path.join(TMP, "lj.db")
os.environ["LJ_DB"] = DB
os.environ["LJ_SALT"] = "test-salt"
os.environ["LJ_COUNT_START"] = "0"
os.environ.pop("LJ_DEV_CORS", None)

sys.path.insert(0, ROOT)
import app  # noqa: E402


def request(port, method, path, body=None, headers=None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
        hdrs["Content-Length"] = str(len(data))
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers=hdrs, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), raw
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


def body_json(raw):
    return json.loads(raw.decode())


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.make_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        os.environ.pop("LJ_DEV_CORS", None)
        conn = app.connect()
        try:
            conn.execute("DELETE FROM entries")
            conn.execute("DELETE FROM visits")
            conn.execute("DELETE FROM posts")
            conn.execute("UPDATE meta SET v = '0' WHERE k = 'count'")
            conn.commit()
        finally:
            conn.close()

    def hit(self, method, path, body=None, headers=None):
        return request(self.port, method, path, body, headers)

    def sign(self, name="ada", msg="hello", hp="", t=3000, ip="203.0.113.10", path="/guestbook"):
        return self.hit(
            "POST",
            path,
            {"name": name, "msg": msg, "hp": hp, "t": t},
            {"Cf-Connecting-Ip": ip},
        )

    def test_health_prefix_and_headers(self):
        for path in ("/health", "/api/health", "/v1/api/health"):
            status, headers, raw = self.hit("GET", path)
            self.assertEqual(status, 200, path)
            self.assertEqual(body_json(raw), {"ok": True})
            self.assertIn("application/json", headers["Content-Type"])
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_visit_get_does_not_increment(self):
        status, _, raw = self.hit("GET", "/visit")
        self.assertEqual(status, 200)
        self.assertEqual(body_json(raw), {"count": 0})
        status, _, raw = self.hit("GET", "/api/visit")
        self.assertEqual(body_json(raw)["count"], 0)

    def test_visit_increment_dedupe_and_bots(self):
        headers = {"Cf-Connecting-Ip": "203.0.113.4", "User-Agent": "Mozilla/5.0"}
        status, _, raw = self.hit("POST", "/visit", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(body_json(raw)["count"], 1)
        status, _, raw = self.hit("POST", "/api/visit", headers=headers)
        self.assertEqual(body_json(raw)["count"], 1)
        status, _, raw = self.hit("GET", "/visit")
        self.assertEqual(body_json(raw)["count"], 1)
        for ua in ("Googlebot", "spider", "slurp", "HeadlessChrome", "Slack preview"):
            status, _, raw = self.hit(
                "POST",
                "/visit",
                headers={"Cf-Connecting-Ip": "203.0.113.4", "User-Agent": ua},
            )
            self.assertEqual(body_json(raw)["count"], 1, ua)
        status, _, raw = self.hit(
            "POST",
            "/visit",
            headers={"Cf-Connecting-Ip": "203.0.113.5", "User-Agent": "Mozilla/5.0"},
        )
        self.assertEqual(body_json(raw)["count"], 2)
        # X-Forwarded-For is not a visitor identity.
        status, _, raw = self.hit(
            "POST",
            "/visit",
            headers={"X-Forwarded-For": "198.51.100.9", "User-Agent": "Mozilla/5.0"},
        )
        first = body_json(raw)["count"]
        status, _, raw = self.hit(
            "POST",
            "/visit",
            headers={"X-Forwarded-For": "198.51.100.10", "User-Agent": "Mozilla/5.0"},
        )
        self.assertEqual(body_json(raw)["count"], first)

    def test_visit_window_expires(self):
        headers = {"Cf-Connecting-Ip": "203.0.113.8", "User-Agent": "Mozilla/5.0"}
        self.hit("POST", "/visit", headers=headers)
        conn = app.connect()
        try:
            conn.execute("UPDATE visits SET seen = ?", (int(time.time()) - 1801,))
            conn.commit()
        finally:
            conn.close()
        status, _, raw = self.hit("POST", "/visit", headers=headers)
        self.assertEqual(body_json(raw)["count"], 2)

    def test_pending_not_visible_until_approved(self):
        status, _, raw = self.sign(ip="203.0.113.20")
        self.assertEqual(status, 202)
        self.assertEqual(body_json(raw), {"status": "pending"})
        status, _, raw = self.hit("GET", "/guestbook")
        self.assertEqual(body_json(raw)["entries"], [])
        status, _, raw = self.hit("GET", "/api/guestbook")
        self.assertEqual(body_json(raw)["entries"], [])
        listed = subprocess.run(
            [sys.executable, "app.py", "list", "--pending"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("ada", listed.stdout)
        self.assertIn("pending", listed.stdout)
        approved = subprocess.run(
            [sys.executable, "app.py", "list"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(approved.stdout.strip(), "")
        entry_id = listed.stdout.split("\t", 1)[0]
        done = subprocess.run(
            [sys.executable, "app.py", "approve", entry_id],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(done.stdout.strip(), "approved")
        status, _, raw = self.hit("GET", "/api/guestbook")
        entries = body_json(raw)["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "ada")
        self.assertEqual(entries[0]["msg"], "hello")
        self.assertRegex(entries[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(entries[0]["date"], app.utc_day())
        hidden = subprocess.run(
            [sys.executable, "app.py", "list", "--pending"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(hidden.stdout.strip(), "")

    def test_honeypot_and_timing_store_nothing(self):
        for hp, t in (("http://spam", 3000), (" ", 4000), ("", 2499), ("", 0), ("", None)):
            payload = {"name": "ada", "msg": "hello", "hp": hp}
            if t is not None:
                payload["t"] = t
            status, _, raw = self.hit(
                "POST",
                "/guestbook",
                payload,
                {"Cf-Connecting-Ip": "203.0.113.30"},
            )
            self.assertEqual(status, 202, payload)
            self.assertEqual(body_json(raw), {"status": "pending"})
        status, _, raw = self.sign(t=2500, ip="203.0.113.31")
        self.assertEqual(status, 202)
        conn = app.connect()
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)

    def test_links_rejected(self):
        samples = (
            "see http://example.com",
            "see HTTPS://example.com",
            "visit www.example.com",
            "go to example.com/page",
            "look at a.bit.ly/x",
        )
        for msg in samples:
            status, headers, raw = self.sign(msg=msg, ip="203.0.113.40")
            self.assertEqual(status, 400, msg)
            self.assertEqual(body_json(raw), {"error": "no links please"})
            self.assertEqual(headers["Cache-Control"], "no-store")
        status, _, raw = self.sign(name="http://nope", msg="fine", ip="203.0.113.41")
        self.assertEqual(status, 400)
        # A link is rejected even when the honeypot is also filled.
        status, _, raw = self.sign(msg="http://x", hp="filled", t=100, ip="203.0.113.42")
        self.assertEqual(status, 400)
        self.assertEqual(body_json(raw)["error"], "no links please")
        status, _, raw = self.sign(msg="hello.com is fine", ip="203.0.113.43")
        self.assertEqual(status, 202)
        conn = app.connect()
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)

    def test_validation_trim_and_control_chars(self):
        status, _, raw = self.sign(name="  ", msg="hi", ip="203.0.113.50")
        self.assertEqual(status, 400)
        status, _, raw = self.sign(name="a" * 33, msg="hi", ip="203.0.113.50")
        self.assertEqual(status, 400)
        status, _, raw = self.sign(name="a" * 32, msg="b" * 141, ip="203.0.113.50")
        self.assertEqual(status, 400)
        status, _, raw = self.sign(name="a" * 32, msg="b" * 140, ip="203.0.113.51")
        self.assertEqual(status, 202)
        status, _, raw = self.sign(name="a\x00b\n", msg="c\x7fd", ip="203.0.113.52")
        self.assertEqual(status, 202)
        conn = app.connect()
        try:
            row = conn.execute(
                "SELECT name, msg FROM entries WHERE iphash = ?",
                (app.ip_hash("203.0.113.52"),),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["name"], "ab")
        self.assertEqual(row["msg"], "cd")
        status, _, raw = self.hit(
            "POST",
            "/guestbook",
            {"name": 1, "msg": "hi", "hp": "", "t": 3000},
        )
        self.assertEqual(status, 400)

    def test_rate_limit(self):
        ip = "203.0.113.60"
        for i in range(3):
            status, _, raw = self.sign(name=f"n{i}", msg="ok", ip=ip)
            self.assertEqual(status, 202, i)
        status, headers, raw = self.sign(name="n3", msg="nope", ip=ip)
        self.assertEqual(status, 429)
        self.assertEqual(body_json(raw), {"error": "slow down"})
        self.assertEqual(headers["Cache-Control"], "no-store")
        conn = app.connect()
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM entries WHERE iphash = ?",
                (app.ip_hash(ip),),
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 3)
        # A different visitor is not limited by the first.
        status, _, raw = self.sign(name="other", msg="ok", ip="203.0.113.61")
        self.assertEqual(status, 202)
        # Honeypot and fast submits do not consume the quota.
        ip = "203.0.113.62"
        for _ in range(4):
            status, _, _ = self.sign(hp="bot", ip=ip)
            self.assertEqual(status, 202)
        for i in range(3):
            status, _, _ = self.sign(name=f"q{i}", msg="ok", ip=ip)
            self.assertEqual(status, 202)
        status, _, raw = self.sign(name="q3", msg="nope", ip=ip)
        self.assertEqual(status, 429)

    def test_reject_and_cli_count(self):
        self.sign(name="gone", msg="bye", ip="203.0.113.70")
        listed = subprocess.run(
            [sys.executable, "app.py", "list", "--pending"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        entry_id = listed.stdout.split("\t", 1)[0]
        done = subprocess.run(
            [sys.executable, "app.py", "reject", entry_id],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(done.stdout.strip(), "rejected")
        status, _, raw = self.hit("GET", "/guestbook")
        self.assertEqual(body_json(raw)["entries"], [])
        again = subprocess.run(
            [sys.executable, "app.py", "list", "--pending"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(again.stdout.strip(), "")
        missing = subprocess.run(
            [sys.executable, "app.py", "approve", "9999"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(missing.returncode, 1)
        self.hit("POST", "/visit", headers={"Cf-Connecting-Ip": "203.0.113.71", "User-Agent": "Mozilla/5.0"})
        counted = subprocess.run(
            [sys.executable, "app.py", "count"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(counted.stdout.strip(), "1")

    def test_newest_first_max_50_pending_excluded(self):
        conn = app.connect()
        try:
            now = int(time.time())
            for i in range(55):
                conn.execute(
                    "INSERT INTO entries (name, msg, date, status, iphash, created) "
                    "VALUES (?, ?, '2026-11-16', 'approved', 'abc', ?)",
                    (f"n{i}", f"m{i}", now + i),
                )
            conn.execute(
                "INSERT INTO entries (name, msg, date, status, iphash, created) "
                "VALUES ('hidden', 'nope', '2026-11-16', 'pending', 'abc', ?)",
                (now + 100,),
            )
            conn.commit()
        finally:
            conn.close()
        status, _, raw = self.hit("GET", "/guestbook")
        entries = body_json(raw)["entries"]
        self.assertEqual(len(entries), 50)
        self.assertEqual(entries[0]["name"], "n54")
        self.assertEqual(entries[-1]["name"], "n5")
        self.assertTrue(all(entry["name"] != "hidden" for entry in entries))
        self.assertGreater(entries[0]["id"], entries[1]["id"])

    def test_body_size_content_type_methods(self):
        big = b'{"name":"a","msg":"b","hp":"","t":3000,"pad":"' + b"x" * 2100
        status, _, raw = self.hit(
            "POST",
            "/guestbook",
            big,
            {"Content-Type": "application/json", "Cf-Connecting-Ip": "203.0.113.80"},
        )
        self.assertEqual(status, 413)
        status, _, raw = self.hit(
            "POST",
            "/api/guestbook",
            b'{"name":"a","msg":"hi","hp":"","t":3000}',
            {"Content-Type": "text/plain", "Cf-Connecting-Ip": "203.0.113.80"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body_json(raw)["error"], "json only")
        status, _, raw = self.hit(
            "POST",
            "/guestbook",
            b"{",
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        status, _, raw = self.hit(
            "POST",
            "/guestbook",
            {"name": "ada", "msg": "charset", "hp": "", "t": 3000},
            {"Content-Type": "application/json; charset=utf-8", "Cf-Connecting-Ip": "203.0.113.81"},
        )
        self.assertEqual(status, 202)
        for method, path in (("PUT", "/guestbook"), ("DELETE", "/visit"), ("PATCH", "/api/health")):
            status, headers, raw = self.hit(method, path)
            self.assertEqual(status, 405, (method, path))
            self.assertEqual(headers["Cache-Control"], "no-store")
        status, _, raw = self.hit("GET", "/nope")
        self.assertEqual(status, 404)
        status, _, raw = self.hit("POST", "/health")
        self.assertEqual(status, 405)

    def test_no_raw_ip_and_truncated_hash(self):
        ip = "203.0.113.99"
        self.sign(ip=ip)
        self.hit("POST", "/visit", headers={"Cf-Connecting-Ip": ip, "User-Agent": "Mozilla/5.0"})
        conn = app.connect()
        try:
            hashes = [row[0] for row in conn.execute("SELECT iphash FROM entries")]
            hashes += [row[0] for row in conn.execute("SELECT iphash FROM visits")]
        finally:
            conn.close()
        self.assertTrue(hashes)
        for hashed in hashes:
            self.assertEqual(len(hashed), 16)
            self.assertNotIn(ip, hashed)
            int(hashed, 16)
        blob = open(DB, "rb").read()
        self.assertNotIn(ip.encode(), blob)

    def test_prefix_agnostic_post(self):
        status, _, raw = self.sign(path="/api/guestbook", ip="203.0.113.15", name="via-api")
        self.assertEqual(status, 202)
        status, _, raw = self.sign(path="/guestbook", ip="203.0.113.16", name="via-root")
        self.assertEqual(status, 202)
        conn = app.connect()
        try:
            names = [row[0] for row in conn.execute("SELECT name FROM entries ORDER BY id")]
        finally:
            conn.close()
        self.assertEqual(names, ["via-api", "via-root"])

    def test_cors_only_when_enabled(self):
        status, headers, _ = self.hit("OPTIONS", "/guestbook")
        self.assertEqual(status, 405)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        os.environ["LJ_DEV_CORS"] = "1"
        try:
            status, headers, raw = self.hit("OPTIONS", "/api/guestbook")
            self.assertEqual(status, 204)
            self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
            self.assertIn("POST", headers["Access-Control-Allow-Methods"])
            status, headers, raw = self.hit("GET", "/health")
            self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        finally:
            os.environ.pop("LJ_DEV_CORS", None)
        status, headers, _ = self.hit("GET", "/health")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_concurrent_visits(self):
        errors = []

        def one(i):
            try:
                status, _, raw = self.hit(
                    "POST",
                    "/visit",
                    headers={"Cf-Connecting-Ip": f"203.0.113.{i}", "User-Agent": "Mozilla/5.0"},
                )
                if status != 200:
                    errors.append(status)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=one, args=(i,)) for i in range(20, 40)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(errors, [])
        status, _, raw = self.hit("GET", "/visit")
        self.assertEqual(body_json(raw)["count"], 20)

    def test_count_seed_in_fresh_process(self):
        db = os.path.join(TMP, "seed.db")
        env = os.environ.copy()
        env["LJ_DB"] = db
        env["LJ_COUNT_START"] = "17"
        env["LJ_SALT"] = "seed-salt"
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import app; s=app.make_server('127.0.0.1', 0); print(s.server_address[1], flush=True); s.serve_forever()",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            port = int(proc.stdout.readline().strip())
            status, _, raw = request(port, "GET", "/api/visit")
            self.assertEqual(status, 200)
            self.assertEqual(body_json(raw)["count"], 17)
            status, _, raw = request(
                port,
                "POST",
                "/visit",
                headers={"Cf-Connecting-Ip": "198.51.100.2", "User-Agent": "Mozilla/5.0"},
            )
            self.assertEqual(body_json(raw)["count"], 18)
            status, _, raw = request(
                port,
                "POST",
                "/visit",
                headers={"Cf-Connecting-Ip": "198.51.100.2", "User-Agent": "Googlebot/2.1"},
            )
            self.assertEqual(body_json(raw)["count"], 18)
        finally:
            proc.terminate()
            proc.wait(5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
