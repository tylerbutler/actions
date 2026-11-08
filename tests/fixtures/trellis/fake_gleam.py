#!/usr/bin/env python3
"""A local-only Gleam stand-in for trellis publication tests."""
import json
import os
import sys
import tomllib
import urllib.request
from pathlib import Path

root = Path(os.environ["FAKE_GLEAM_ROOT"])
manifest = Path("gleam.toml").read_text()
meta = tomllib.loads(manifest)
with (root / "gleam-log").open("a") as log:
    log.write(json.dumps({"name": meta["name"], "args": sys.argv[1:],
                          "sources": sorted(str(p) for p in Path("src").rglob("*.gleam"))}) + "\n")
if sys.argv[1] == "publish":
    (root / f"published-{meta['name']}.toml").write_text(manifest)
    if meta["name"] == os.environ.get("FAIL_PACKAGE") and not (root / "failed-once").exists():
        (root / "failed-once").touch()
        sys.exit(1)
    data = json.dumps({"name": meta["name"], "version": meta["version"]}).encode()
    request = urllib.request.Request(os.environ["FAKE_HEX_URL"] + "/publish", data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        assert response.status == 201
