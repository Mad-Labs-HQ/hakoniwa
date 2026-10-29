"""Check the exact baseline inputs used by the isolated registry rehearsal.

These transformations affect disposable manifests only. The package identity,
features and every unrelated manifest or lockfile entry must remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import tomllib

NAME = "mad-hakoniwa"
VERSION = "1.8.0-mad.1"
TARGET = 'cfg(target_os = "linux")'


def digest(path: Path) -> str:
    """Identify a retained file by its exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root: Path) -> dict[str, str]:
    """Capture every regular file, so restoration cannot hide an added file."""
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def registry_manifest(text: str) -> str:
    """Change only the current exact Linux fork declaration's source."""
    before = tomllib.loads(text)
    dependency = before["target"][TARGET]["dependencies"]["hakoniwa"]
    allowed = {"package", "version", "path", "features"}
    if (
        set(dependency) != allowed
        or dependency["package"] != NAME
        or dependency["version"] != "=" + VERSION
        or dependency["features"] != ["landlock"]
    ):
        raise ValueError("expected the current exact fork path declaration")
    expected = {key: value for key, value in dependency.items() if key != "path"}
    expected["registry"] = "review"
    line = (
        "hakoniwa = { "
        + ", ".join(f"{key} = {json.dumps(value)}" for key, value in expected.items())
        + " }"
    )
    changed, count = re.subn(
        r"^hakoniwa\s*=\s*\{[^\n]+\}\s*$", line, text, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError("expected one inline hakoniwa declaration")
    before["target"][TARGET]["dependencies"]["hakoniwa"] = expected
    if tomllib.loads(changed) != before:
        raise ValueError("registry rewrite changed unrelated manifest values")
    return changed


def check_lock(before: str, after: str, registry: str, checksum: str) -> None:
    """Permit only registry source/checksum additions to the existing fork."""
    old, new = (tomllib.loads(value) for value in (before, after))
    old_packages, new_packages = old.pop("package"), new.pop("package")
    if old != new:
        raise ValueError("lockfile metadata changed")
    fork_old = [p for p in old_packages if p["name"] == NAME]
    fork_new = [p for p in new_packages if p["name"] == NAME]
    if len(fork_old) != 1 or len(fork_new) != 1:
        raise ValueError("expected one fork in each lockfile")
    source = fork_new[0].get("source")
    if source not in {registry, "registry+" + registry}:
        raise ValueError("lockfile selected a different registry")
    expected = {**fork_old[0], "source": source, "checksum": checksum}
    if fork_new[0] != expected or expected["version"] != VERSION:
        raise ValueError("lockfile changed more than fork source/checksum")
    canonical = lambda rows: sorted(
        json.dumps(p, sort_keys=True) for p in rows if p["name"] != NAME
    )
    if canonical(old_packages) != canonical(new_packages):
        raise ValueError("unrelated locked dependencies changed")


def index_entry(manifest: dict, checksum: str) -> dict:
    """Translate this normalized baseline package into Cargo's index schema."""
    dependencies = []
    for key, kind in (
        ("dependencies", "normal"),
        ("build-dependencies", "build"),
        ("dev-dependencies", "dev"),
    ):
        for name, value in manifest.get(key, {}).items():
            value = {"version": value} if isinstance(value, str) else value
            if "path" in value or "git" in value:
                raise ValueError("registry package retains a path or Git dependency")
            dependencies.append(
                {
                    "name": name,
                    "req": value["version"],
                    "features": value.get("features", []),
                    "optional": value.get("optional", False),
                    "default_features": value.get("default-features", True),
                    "target": None,
                    "kind": kind,
                    "registry": "https://github.com/rust-lang/crates.io-index",
                    "package": value.get("package"),
                }
            )
    if manifest.get("target"):
        raise ValueError(
            "add target-specific index support before changing this baseline"
        )
    if (manifest["package"]["name"], manifest["package"]["version"]) != (NAME, VERSION):
        raise ValueError("archive is not the reviewed baseline")
    return {
        "name": NAME,
        "vers": VERSION,
        "deps": dependencies,
        "cksum": checksum,
        "features": {},
        "features2": manifest.get("features", {}),
        "v": 2,
        "yanked": False,
    }
