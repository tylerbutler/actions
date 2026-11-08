import hashlib
import importlib.util
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("trellis_install", Path(__file__).with_name("install.py"))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.mark.parametrize("raw", ["", "latest", "1", "1.3", "../1.3.0", "v01.3.0",
                                     "1.3.0;echo bad", "1.3.0-rc.01"])
def test_invalid_version(raw):
    with pytest.raises(ValueError):
        installer.version(raw)


@pytest.mark.parametrize("raw", ["1.3.0", "v1.3.0", "1.3.0-rc.0"])
def test_version(raw):
    assert installer.version(raw) == raw.removeprefix("v")


@pytest.mark.parametrize("system,machine,triple", [
    ("Linux", "x86_64", "x86_64-unknown-linux-gnu"),
    ("Linux", "aarch64", "aarch64-unknown-linux-gnu"),
    ("Darwin", "arm64", "aarch64-apple-darwin"),
    ("Darwin", "x86_64", "x86_64-apple-darwin"),
    ("Windows", "AMD64", "x86_64-pc-windows-msvc"),
])
def test_platform(system, machine, triple):
    assert installer.target(system, machine)[0] == triple


@pytest.mark.parametrize("system,machine", [("Windows", "arm64"), ("Linux", "i686"),
                                           ("FreeBSD", "x86_64")])
def test_unsupported_platform(system, machine):
    with pytest.raises(ValueError):
        installer.target(system, machine)


def test_zip_extract_ignores_other_files(tmp_path):
    archive = tmp_path / "binary.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("trellis.exe", b"binary")
        bundle.writestr("../escaped", b"bad")
    installer.extract(archive, "root", "trellis.exe", tmp_path / "trellis.exe")
    assert (tmp_path / "trellis.exe").read_bytes() == b"binary"
    assert not (tmp_path.parent / "escaped").exists()


@pytest.mark.parametrize("problem", ["download", "checksum", "version", None])
@pytest.mark.parametrize("system,machine", [("Linux", "x86_64"), ("Windows", "AMD64")])
def test_install_and_cleanup(tmp_path, problem, system, machine):
    triple, extension, binary = installer.target(system, machine)
    asset_root = f"trellis-gleam-{triple}"
    asset = f"{asset_root}.{extension}"
    buffer = io.BytesIO()
    if extension == "zip":
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr(binary, b"binary")
    else:
        with tarfile.open(fileobj=buffer, mode="w:xz") as bundle:
            member = tarfile.TarInfo(f"{asset_root}/{binary}")
            member.size = 6
            bundle.addfile(member, io.BytesIO(b"binary"))
    archive = buffer.getvalue()

    def download(url, destination):
        assert url.endswith(f"/v1.3.0/{asset}") or url.endswith(f"/v1.3.0/{asset}.sha256")
        if problem == "download":
            raise OSError("download failed")
        if url.endswith(".sha256"):
            destination.write_text(("0" * 64 if problem == "checksum" else
                                    hashlib.sha256(archive).hexdigest()) + "  binary")
        else:
            destination.write_bytes(archive)

    with patch.object(installer.platform, "system", return_value=system), \
         patch.object(installer.platform, "machine", return_value=machine), \
         patch.object(installer, "download", side_effect=download), \
         patch.object(installer.subprocess, "run", return_value=subprocess.CompletedProcess(
             [], 0, "trellis 1.2.0" if problem == "version" else "trellis 1.3.0", "")):
        if problem:
            with pytest.raises((OSError, ValueError)):
                installer.install("v1.3.0", tmp_path)
            assert list(tmp_path.iterdir()) == []
        else:
            version, path = installer.install("v1.3.0", tmp_path)
            assert version == "1.3.0"
            assert path.name == binary
            assert path.read_bytes() == b"binary"


def test_path_and_outputs(tmp_path, monkeypatch):
    binary = tmp_path / "bin" / "trellis"
    monkeypatch.setenv("GITHUB_PATH", str(tmp_path / "path"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    with patch.object(installer, "install", return_value=("1.3.0", binary)):
        installer.main()
    assert (tmp_path / "path").read_text() == f"{binary.parent}\n"
    assert (tmp_path / "outputs").read_text() == f"version=1.3.0\npath={binary}\n"
