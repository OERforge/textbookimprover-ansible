#!/usr/bin/env python3
"""util/update-pins.py's parts that need no network, on a copy of the
roles: where a new pin goes, that a pin is never replaced, how a default is
set, how versions are ordered, and that a token isn't sent on where a
redirect points (with two servers of its own on 127.0.0.1). Needs PyYAML."""

import http.server
import importlib.util
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(os.path.dirname(HERE))

spec = importlib.util.spec_from_file_location("update_pins", os.path.join(TOP, "util", "update-pins.py"))
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)

failures = 0


def check(what, ok):
    global failures
    print(("ok   " if ok else "FAIL ") + what)
    failures += not ok


def stops(call):
    try:
        call()
    except up.Stop:
        return True
    return False


with tempfile.TemporaryDirectory() as scratch:
    shutil.copytree(os.path.join(TOP, "roles"), os.path.join(scratch, "roles"))
    up.ROLES = os.path.join(scratch, "roles")
    path = up.role_file("pandoc", "vars", "pins.yml")
    before = open(path, encoding="utf-8").read()
    pinned = up.pins("pandoc")["pandoc_pins"]["3.14"]

    up.settle("pandoc", "pandoc_pins", "3.15", "ab" * 32, single="ab" * 32)
    after = open(path, encoding="utf-8").read()
    check("a new pin goes first under its map, and nothing else changes",
          after == before.replace('pandoc_pins:\n', 'pandoc_pins:\n  "3.15": ' + "ab" * 32 + "\n", 1))
    check("and reads back", up.pins("pandoc")["pandoc_pins"]["3.15"] == "ab" * 32)

    up.settle("pandoc", "pandoc_pins", "3.14", pinned, single=pinned)
    check("a pin already there that matches is left as it is",
          open(path, encoding="utf-8").read() == after)
    check("a pin is never replaced: a different value stops the script",
          stops(lambda: up.settle("pandoc", "pandoc_pins", "3.14", "cd" * 32, single="cd" * 32))
          and up.pins("pandoc")["pandoc_pins"]["3.14"] == pinned)

    up.settle("browser_checks", "node_pins", "99.0.0", {"sha256": "ef" * 32, "signer": "F" * 40},
              ["sha256: " + "ef" * 32, "signer: " + "F" * 40])
    check("a pin of several fields reads back as a mapping",
          up.pins("browser_checks")["node_pins"]["99.0.0"] == {"sha256": "ef" * 32, "signer": "F" * 40})
    up.write_pin("browser_checks", "greenlet_pins", "9.9.9", items=["0a" * 32, "1" * 64])
    check("a pin of a list reads back as a list, a hash of digits alone as text",
          up.pins("browser_checks")["greenlet_pins"]["9.9.9"] == ["0a" * 32, "1" * 64])
    check("a map the file hasn't stops the script",
          stops(lambda: up.write_pin("pandoc", "no_such_pins", "1", single="x")))

    up.set_default("tex", "tex_snapshot", "2099-01-02")
    check("a snapshot's date is a default like a version", up.defaults("tex")["tex_snapshot"] == "2099-01-02")
    up.settle("tex", "tex_snapshot_pins", "2099-01-02", "ab" * 64, single="ab" * 64)
    check("and its pin is found by date", up.is_pinned("tex_snapshot", "2099-01-02")
          and not up.is_pinned("tex_snapshot", "2099-01-03"))
    check("what isn't a date stops the script before anything is downloaded",
          stops(lambda: up.add_tex_snapshot("2099-1-2", scratch, None))
          and stops(lambda: up.add_tex_snapshot("../../x", scratch, None)))

    up.set_default("validators", "vnu_default_version", "99.1.1")
    check("a default is set where it's a plain version", up.defaults("validators")["vnu_default_version"] == "99.1.1")
    check("and a default the file hasn't stops the script",
          stops(lambda: up.set_default("validators", "no_such_version", "1")))

check("versions are ordered by their numbers, and dates by theirs",
      up.version_key("2026-11-21") > up.version_key("2026-11-20") > up.version_key("2026-10-31")
      and up.version_key("3.10") > up.version_key("3.9")
      and up.version_key("v2026.11") > up.version_key("v2026.09"))
check("only releases count as stable", up.stable("3.14") and up.stable("v0.10")
      and not up.stable("pandoc-server-0.1.4") and not up.stable("27.0.0-alpha.0"))
check("the scratch copy was used, not the collection's roles",
      up.pins.__module__ == "update_pins" and "3.15" not in open(
          os.path.join(TOP, "roles", "pandoc", "vars", "pins.yml"), encoding="utf-8").read())



# A server that redirects, and one it redirects to, each noting what it got.
seen = {}


def server(name, answer):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen[name] = self.headers.get("Authorization")
            answer(self)

        def log_message(self, *args):
            pass
    s = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def landing(handler):
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(b"{}")


there = server("there", landing)


def redirect(handler):
    handler.send_response(302)
    handler.send_header("Location", f"http://127.0.0.1:{there.server_port}/")
    handler.end_headers()


here = server("here", redirect)
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1"
up.fetch_json(f"http://127.0.0.1:{here.server_port}/", {"Accept": "application/json"},
              {"Authorization": "Bearer t0ken"})
check("a token goes to the address asked", seen.get("here") == "Bearer t0ken")
check("and not on to where it redirects", "there" in seen and seen["there"] is None)
here.shutdown()
there.shutdown()

sys.exit(1 if failures else 0)
