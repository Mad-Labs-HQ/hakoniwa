"""Recover upstream source from the repair record and check optional qualification.

The basic proof needs only repository product files. Source inventories and patch
series are explicit inputs; internal evidence is never discovered implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def verify(source_inventory: Path | None, patch_series: list[Path]) -> dict:
    """Check upstream recovery, plus each qualification record the caller selects."""
    crate = ROOT / "hakoniwa"
    reference = json.loads((crate / "UPSTREAM-CHECKSUMS.json").read_text())
    if reference["upstream_version"] != "1.8.0":
        raise ValueError("provenance does not describe the intended upstream release")
    package = tomllib.loads((crate / "Cargo.toml").read_text())["package"]
    if (package["name"], package["version"], package["publish"]) != (
        "mad-hakoniwa",
        "1.8.0-mad.1",
        False,
    ):
        raise ValueError("candidate identity or publication guard changed")
    actual = {
        str(path.relative_to(crate)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [*sorted((crate / "src").rglob("*.rs")), crate / "build.rs"]
    }
    if source_inventory is not None and actual != json.loads(
        source_inventory.read_text()
    ):
        raise ValueError("live library differs from the qualified source inventory")
    if (
        hashlib.sha256((crate / "LICENSE").read_bytes()).hexdigest()
        != reference["files"]["LICENSE"]
    ):
        raise ValueError("original LGPL license changed")
    with tempfile.TemporaryDirectory(prefix="mad-hakoniwa-provenance-") as temporary:
        work = Path(temporary)
        shutil.copytree(crate / "src", work / "src")
        subprocess.run(
            ["git", "apply", "--reverse", str(crate / "PATCH.diff")],
            cwd=work,
            check=True,
        )
        recovered = {
            str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (work / "src").rglob("*")
            if path.is_file()
        }
        expected = {
            name: digest
            for name, digest in reference["files"].items()
            if name.startswith("src/")
        }
        if recovered != expected:
            raise ValueError("reversed patch does not recover the published source")
    for manifest in patch_series:
        series = json.loads(manifest.read_text())
        for row in series["patches"]:
            patch = manifest.parent / (row["label"] + ".patch")
            if hashlib.sha256(patch.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"patch hash drifted: {patch}")
    return {
        "status": "passed",
        "upstream_version": "1.8.0",
        "library_rust_files": len(actual) - 1,
        "source_inventory_checked": source_inventory is not None,
        "patch_series_checked": len(patch_series),
        "original_license_match": True,
        "reversed_patch_matches_published_source": True,
    }


def main() -> None:
    """Keep optional historical checks explicit, so a clean clone can verify source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-inventory", type=Path)
    parser.add_argument("--patch-series", type=Path, action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(verify(args.source_inventory, args.patch_series), indent=2))


if __name__ == "__main__":
    main()
