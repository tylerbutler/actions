"""Controlled repositories and local APIs; no production publication."""

import json
import os
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def workspace(root: Path, *, bundle=False):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "gleam.toml").write_text(
        '[tools.trellis]\nmembers=["packages/*"]\n'
        '[tools.trellis.publish]\npackage_tags=["exact","minor"]\n'
        'retry={attempts=1,initial_delay="1ms",multiplier=1}\n' +
        ('bundle={app=["private"]}\n' if bundle else "") +
        '[tools.trellis.publish.lifecycle]\n'
        'packages={"packages/private"="workspace","packages/tool"="git_only"}\n'
    )
    for name in ("core", "app", "private", "tool"):
        pkg = root / "packages" / name
        (pkg / "src").mkdir(parents=True)
        dependency = "private" if bundle and name == "app" else "core"
        (pkg / "gleam.toml").write_text(f'name="{name}"\nversion="1.0.0"\n' +
            (f'[dependencies]\n{dependency}={{path="../{dependency}"}}\n' if name == "app" else ""))
        (pkg / "src" / f"{name}.gleam").write_text("pub fn demo() { 1 }\n")
        (pkg / "CHANGELOG.md").write_text("# Changelog\n\n## v1.0.0\n\n- initial\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def local_env():
    return {key: value for key, value in {**os.environ, "CI": "true"}.items()
            if key.lower() not in ("http_proxy", "https_proxy", "all_proxy")}


def invoke(root, args, env=None):
    return subprocess.run([os.environ["TRELLIS_TEST_BIN"], *args], cwd=root, text=True,
                          capture_output=True, env={**local_env(), **(env or {})})


@contextmanager
def api():
    releases = {}
    versions = {}
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if "/packages/" in self.path:
                name = self.path.rsplit("/", 1)[1]
                self.respond(200, {"releases": [{"version": v} for v in versions.get(name, [])]})
            elif "/releases/tags/" in self.path:
                tag = self.path.split("/releases/tags/", 1)[1]
                self.respond(200 if tag in releases else 404, releases.get(tag, {}))
            else:
                self.respond(404, {})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/publish":
                versions.setdefault(payload["name"], []).append(payload["version"])
                self.respond(201, {})
                return
            requests.append(payload)
            releases[payload["tag_name"]] = payload
            self.respond(201, payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", versions, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
