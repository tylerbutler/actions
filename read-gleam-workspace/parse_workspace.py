#!/usr/bin/env python3
"""Parse a Gleam workspace.toml and output structured package metadata.

Reads a workspace config with glob-enabled member patterns, resolves them
against the filesystem, topologically sorts by intra-workspace dependencies,
and writes structured outputs for GitHub Actions consumption (or prints them
to stdout when GITHUB_OUTPUT is not set).

Environment variables:
    WORKSPACE_FILE  Path to workspace.toml (required)
    TAG_NAME        Optional git tag to map to a workspace package
    TAG_PREFIX      Optional prefix to strip before matching package names
    GITHUB_OUTPUT   GitHub Actions output file (optional; prints to stdout if unset)
"""

import glob
import json
import os
import re
import sys
import tomllib
from collections import deque


VALID_PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_PACKAGE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


def parse_workspace(workspace_file: str) -> list[dict]:
    """Parse workspace.toml and return a topologically sorted list of package metadata."""
    with open(workspace_file, "rb") as f:
        config = tomllib.load(f)

    ws = config.get("workspace", {})
    members = ws.get("members", [])
    excludes = ws.get("exclude", [])

    # Expand members: literal paths kept in order, globs expanded + sorted
    expanded: list[str] = []
    for pattern in members:
        if any(c in pattern for c in ("*", "?", "[")):
            matched = sorted(glob.glob(pattern))
            for m in matched:
                if os.path.isdir(m) and os.path.isfile(
                    os.path.join(m, "gleam.toml")
                ):
                    expanded.append(m)
        else:
            if os.path.isdir(pattern) and os.path.isfile(
                os.path.join(pattern, "gleam.toml")
            ):
                expanded.append(pattern)
            elif pattern == "." and os.path.isfile("gleam.toml"):
                expanded.append(".")
            else:
                print(f"::warning::Member '{pattern}' has no gleam.toml, skipping")

    # Apply excludes
    for exc in excludes:
        if any(c in exc for c in ("*", "?", "[")):
            exc_matches = set(glob.glob(exc))
            expanded = [p for p in expanded if p not in exc_matches]
        else:
            expanded = [p for p in expanded if p != exc]

    if not expanded:
        print("::error::No packages found after expanding workspace members")
        sys.exit(1)

    # Read name, version, and dependencies from each gleam.toml
    packages: list[dict] = []
    for pkg_path in expanded:
        if not is_safe_package_path(pkg_path):
            print("::error::Invalid package path")
            sys.exit(1)
        toml_path = (
            os.path.join(pkg_path, "gleam.toml") if pkg_path != "." else "gleam.toml"
        )
        with open(toml_path, "rb") as f:
            pkg_config = tomllib.load(f)
        name = pkg_config.get("name", "")
        version = pkg_config.get("version", "")
        deps = list(pkg_config.get("dependencies", {}).keys())
        if not name:
            print(f"::warning::No 'name' in {toml_path}, skipping")
            continue
        if not VALID_PACKAGE_NAME.fullmatch(name):
            print(f"::error::Invalid package name in {toml_path}")
            sys.exit(1)
        packages.append({
            "name": name,
            "path": pkg_path,
            "version": version,
            "deps": deps,
        })

    packages = _topo_sort(packages)

    # Strip internal deps field from output
    for p in packages:
        del p["deps"]

    return packages


def is_safe_package_path(path: str) -> bool:
    """Return whether a workspace package path is safe to emit as an action output."""
    if os.path.isabs(path) or not VALID_PACKAGE_PATH.fullmatch(path):
        return False
    return ".." not in path.split("/")


def _topo_sort(packages: list[dict]) -> list[dict]:
    """Topologically sort packages by intra-workspace dependencies (Kahn's algorithm).

    Only considers dependencies between workspace members. External deps are ignored.
    Packages with no intra-workspace dependencies come first. Among packages at the
    same depth, the original discovery order is preserved for stability.
    """
    ws_names = {p["name"] for p in packages}
    by_name = {p["name"]: p for p in packages}

    # Build adjacency: edges point from dependency → dependent
    in_degree: dict[str, int] = {p["name"]: 0 for p in packages}
    dependents: dict[str, list[str]] = {p["name"]: [] for p in packages}

    for p in packages:
        for dep in p["deps"]:
            if dep in ws_names:
                in_degree[p["name"]] += 1
                dependents[dep].append(p["name"])

    # Seed queue with packages that have no intra-workspace deps, in original order
    queue: deque[str] = deque(
        p["name"] for p in packages if in_degree[p["name"]] == 0
    )
    sorted_pkgs: list[dict] = []

    while queue:
        name = queue.popleft()
        sorted_pkgs.append(by_name[name])
        for dep_name in dependents[name]:
            in_degree[dep_name] -= 1
            if in_degree[dep_name] == 0:
                queue.append(dep_name)

    if len(sorted_pkgs) != len(packages):
        cycle_members = [p["name"] for p in packages if in_degree[p["name"]] > 0]
        print(f"::error::Circular dependency detected among: {', '.join(cycle_members)}")
        sys.exit(1)

    return sorted_pkgs


def build_outputs(packages: list[dict]) -> dict[str, str]:
    """Build output strings from package metadata."""
    packages_str = " ".join(p["path"] for p in packages)
    projects_str = ",".join(p["name"] for p in packages)

    version_files_lines = []
    for p in packages:
        toml_rel = (
            os.path.join(p["path"], "gleam.toml") if p["path"] != "." else "gleam.toml"
        )
        version_files_lines.append(f"{p['name']}:{toml_rel}:version")
    version_files_str = "\n".join(version_files_lines)

    cache_globs = []
    for p in packages:
        prefix = p["path"]
        if prefix == ".":
            cache_globs.extend(["gleam.toml", "manifest.toml"])
        else:
            cache_globs.extend(
                [f"{prefix}/gleam.toml", f"{prefix}/manifest.toml"]
            )
    cache_hash_str = ", ".join(f"'{g}'" for g in cache_globs)

    tag_outputs = build_tag_outputs(
        packages,
        os.environ.get("TAG_NAME", ""),
        os.environ.get("TAG_PREFIX", ""),
    )

    return {
        "packages": packages_str,
        "projects": projects_str,
        "version-files": version_files_str,
        "packages-json": json.dumps(packages),
        "cache-hash-globs": cache_hash_str,
        **tag_outputs,
    }


def build_tag_outputs(packages: list[dict], tag_name: str, tag_prefix: str) -> dict[str, str]:
    """Build outputs for the workspace package named by a release tag."""
    if not tag_name:
        return {
            "tag-package": "",
            "tag-package-path": "",
        }

    if tag_prefix:
        if not tag_name.startswith(tag_prefix):
            print(f"::error::Tag '{tag_name}' does not start with prefix '{tag_prefix}'")
            sys.exit(1)
        tag_name = tag_name[len(tag_prefix):]

    for package in packages:
        tag_stem = f"{package['name']}-v"
        if tag_name.startswith(tag_stem) and len(tag_name) > len(tag_stem):
            return {
                "tag-package": package["name"],
                "tag-package-path": package["path"],
            }

    print(f"::error::Tag '{tag_name}' does not match any workspace package")
    sys.exit(1)


def write_github_outputs(outputs: dict[str, str]) -> None:
    """Write outputs to GITHUB_OUTPUT file, or print to stdout."""
    output_file = os.environ.get("GITHUB_OUTPUT")

    if output_file:
        with open(output_file, "a") as out:
            out.write(f"packages={outputs['packages']}\n")
            out.write(f"projects={outputs['projects']}\n")
            out.write(f"version-files<<EOF_VERSION_FILES\n")
            out.write(f"{outputs['version-files']}\n")
            out.write(f"EOF_VERSION_FILES\n")
            out.write(f"packages-json={outputs['packages-json']}\n")
            out.write(f"cache-hash-globs={outputs['cache-hash-globs']}\n")
            out.write(f"tag-package={outputs['tag-package']}\n")
            out.write(f"tag-package-path={outputs['tag-package-path']}\n")
    else:
        for key, value in outputs.items():
            print(f"{key}={value}")


def main() -> None:
    workspace_file = os.environ.get("WORKSPACE_FILE", "workspace.toml")
    packages = parse_workspace(workspace_file)
    outputs = build_outputs(packages)
    write_github_outputs(outputs)

    print(f"Found {len(packages)} package(s):")
    for p in packages:
        print(f"  {p['name']}@{p['version']} ({p['path']})")


if __name__ == "__main__":
    main()
