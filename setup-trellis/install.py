"""Install only the requested, checksum-verified release binary."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary, fail, write_output  # noqa: E402


def version(raw: str) -> str:
    match = re.fullmatch(
        r"v?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)", raw
    )
    if not match:
        raise ValueError("version must be an exact release version, such as 1.3.0")
    result = match[1]
    if "-" in result:
        for identifier in result.split("-", 1)[1].split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise ValueError("numeric prerelease identifiers must not have leading zeros")
    return result


def target(system: str, machine: str) -> tuple[str, str, str]:
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64",
            "arm64": "aarch64"}.get(machine.lower())
    suffix = {"Linux": "unknown-linux-gnu", "Darwin": "apple-darwin",
              "Windows": "pc-windows-msvc"}.get(system)
    if not arch or not suffix or (system == "Windows" and arch != "x86_64"):
        raise ValueError(f"unsupported trellis platform: {system}/{machine}")
    return f"{arch}-{suffix}", "zip" if system == "Windows" else "tar.xz", (
        "trellis.exe" if system == "Windows" else "trellis"
    )


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def extract(archive: Path, asset_root: str, binary: str, destination: Path) -> None:
    member_name = f"{asset_root}/{binary}"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            with bundle.open(member_name) as source, destination.open("wb") as out:
                shutil.copyfileobj(source, out)
    else:
        with tarfile.open(archive) as bundle:
            member = bundle.getmember(member_name)
            if not member.isfile():
                raise ValueError("release binary is not a regular file")
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("release binary is absent")
            with source, destination.open("wb") as out:
                shutil.copyfileobj(source, out)
    destination.chmod(0o755)


def install(raw: str, root: Path) -> tuple[str, Path]:
    requested = version(raw)
    triple, extension, binary = target(platform.system(), platform.machine())
    asset_root = f"trellis-gleam-{triple}"
    asset = f"{asset_root}.{extension}"
    url = f"https://github.com/tylerbutler/trellis/releases/download/v{requested}/{asset}"
    root.mkdir(parents=True, exist_ok=True)
    install_dir = Path(tempfile.mkdtemp(prefix=f"trellis-{requested}-", dir=root))
    try:
        with tempfile.TemporaryDirectory(prefix="trellis-download-", dir=root) as scratch:
            archive = Path(scratch) / asset
            checksum = Path(scratch) / "checksum"
            download(url, archive)
            download(f"{url}.sha256", checksum)
            fields = checksum.read_text().split()
            if not fields or not re.fullmatch(r"[0-9a-fA-F]{64}", fields[0]):
                raise ValueError("release checksum is malformed")
            if hashlib.sha256(archive.read_bytes()).hexdigest() != fields[0].lower():
                raise ValueError("release checksum does not match downloaded archive")
            path = install_dir / binary
            extract(archive, asset_root, binary, path)
        actual = subprocess.run([str(path), "--version"], check=True, text=True,
                                capture_output=True).stdout.strip()
        if not re.fullmatch(rf"trellis {re.escape(requested)}(?: \([^\n]*\))?", actual):
            raise ValueError(f"installed version mismatch: expected {requested}, got {actual!r}")
        return requested, path
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.CalledProcessError):
        shutil.rmtree(install_dir)
        raise


def main() -> None:
    try:
        requested, path = install(os.environ.get("TRELLIS_VERSION", ""),
                                  Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as output:
            output.write(f"{path.parent}\n")
        write_output("version", requested)
        write_output("path", str(path))
        append_summary(f"## Setup trellis\n\nInstalled trellis {requested}.")
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        append_summary("## Setup trellis\n\nInstallation failed.")
        fail(str(error))


if __name__ == "__main__":
    main()
