"""Freeze current product branches and test the archived fork without its checkout.

Run from the fork repository with its declared environment. Only reviewed product
inputs, standalone probes and a crate archive enter the native Linux container.
The source manifest remains publication-blocked; this tool has no upload path.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import tomllib

from tools.registry_support import NAME, VERSION, digest, inventory

ROOT = Path(__file__).resolve().parents[1]


def freeze_product(repo: Path, destination: Path) -> None:
    """Copy tracked and new product inputs without local research or credentials."""
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo,
    )
    for name in sorted(path.decode() for path in raw.split(b"\0") if path):
        relative = Path(name)
        path = repo / relative
        if not path.is_file():
            continue
        if (
            relative.parts[0] in {"sdks", "spikes", "tmp", "target", "vendor"}
            or relative.name == ".envrc"
        ):
            continue
        if (
            relative.parts[0] == "docs"
            and not relative.is_relative_to("docs/rust")
            and relative != Path("docs/hakoniwa-fork.md")
        ):
            continue
        if any(
            part in {"node_modules", "__pycache__", ".git", ".direnv"}
            for part in relative.parts
        ):
            continue
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(
            repo.resolve()
        ):
            raise ValueError(f"product symlink escapes its repository: {path}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main() -> None:
    """Prepare a checked archive, freeze inputs and retain all native results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--source-inventory",
        type=Path,
        required=True,
        help="Qualified library/build-script SHA-256 inventory",
    )
    parser.add_argument(
        "--patch-series",
        type=Path,
        action="append",
        required=True,
        help="Patch-series manifest to verify; repeat for each series",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Verify packaging and freeze inputs without starting Docker",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs, results = out / "inputs", out / "results"
    inputs.mkdir()
    results.mkdir()
    results.chmod(0o777)
    branches = {}
    for name in ("mad-hakoniwa", "mad-sandbox", "mad-run"):
        repo = ROOT.parent / name
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repo, text=True
        ).strip()
        if branch != "codex/prepare-fork":
            raise ValueError(f"wrong branch in {name}: {branch}")
        branches[name] = {
            "branch": branch,
            "revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip(),
        }
    proof = [
        sys.executable,
        "-m",
        "tools.verify_provenance",
        "--source-inventory",
        str(args.source_inventory.resolve(strict=True)),
    ]
    for series in args.patch_series:
        proof.extend(["--patch-series", str(series.resolve(strict=True))])
    subprocess.run(proof, cwd=ROOT, check=True)
    with (out / "package.log").open("w") as log:
        subprocess.run(
            [
                "cargo",
                "package",
                "--locked",
                "--manifest-path",
                "hakoniwa/Cargo.toml",
                "--allow-dirty",
                "--no-verify",
                "--target-dir",
                str(out / "packaging"),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    archive = out / f"packaging/package/{NAME}-{VERSION}.crate"
    with tarfile.open(archive) as package:
        prefix = f"{NAME}-{VERSION}/"
        manifest = tomllib.loads(
            package.extractfile(prefix + "Cargo.toml").read().decode()
        )
        if manifest["package"].get("publish") is not False:
            raise ValueError("archive lost publication guard")
        source_manifest = ROOT / "hakoniwa/Cargo.toml"
        expected_files = {source_manifest}
        for pattern in tomllib.loads(source_manifest.read_text())["package"]["include"]:
            expected_files.update(
                p for p in (ROOT / "hakoniwa").glob(pattern) if p.is_file()
            )
        for source in expected_files:
            relative = source.relative_to(ROOT / "hakoniwa")
            archived = (
                "Cargo.toml.orig" if relative == Path("Cargo.toml") else str(relative)
            )
            if package.extractfile(prefix + archived).read() != source.read_bytes():
                raise ValueError(f"archive differs from live fork: {relative}")
    shutil.copy2(archive, inputs / archive.name)
    for name in ("mad-run", "mad-sandbox"):
        freeze_product(ROOT.parent / name, inputs / name)
    probe = inputs / "registry-probe"
    shutil.copytree(ROOT / "tools/probes/registry-consumer", probe)
    (probe / "src/bin").mkdir()
    shutil.copy2(
        ROOT / "hakoniwa/examples/repair_supervisor.rs", probe / "src/bin/supervisor.rs"
    )
    tests = inputs / "upstream-tests"
    tests.mkdir()
    for name in (
        "ownership_repair.rs",
        "termination_repair.rs",
        "remount_repair.rs",
        "supervisor_repair.rs",
        "overlay_repair.rs",
    ):
        shutil.copy2(ROOT / "hakoniwa/tests" / name, tests / name)
    harness = inputs / "harness"
    harness.mkdir()
    for name in ("run_in_lab.py", "verify_registry.py", "registry_support.py"):
        shutil.copy2(ROOT / "tools" / name, harness / name)
    baseline = {
        "branches": branches,
        "archive_sha256": digest(archive),
        "input_files": inventory(inputs),
        "version": VERSION,
        "publication": False,
        "upgrade_1_8_0": True,
    }
    (inputs / "BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n")
    (out / "BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n")
    if args.prepare_only:
        (out / "PREPARED.json").write_text(
            json.dumps({"status": "prepared", "runtime_tests_run": False}) + "\n"
        )
        print(out, flush=True)
        return
    tag = "mad-run-sdk-test-arm64:latest"
    image = subprocess.check_output(
        ["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True
    ).strip()
    command = [
        "docker",
        "run",
        "--rm",
        "--privileged",
        "--platform",
        "linux/arm64",
        "-v",
        str(inputs) + ":/inputs:ro",
        "-v",
        str(results) + ":/results",
        image,
        "python3",
        "/inputs/harness/run_in_lab.py",
    ]
    (out / "COMMAND.json").write_text(json.dumps(command, indent=2) + "\n")
    (out / "IMAGE.json").write_text(
        json.dumps(
            {
                "image": image,
                "tag": tag,
                "platform": "linux/arm64",
                "outer_container": "privileged",
                "application_user": "tester",
                "fork_checkout_mounted": False,
            }
        )
        + "\n"
    )
    print(out, flush=True)
    with (out / "harness.log").open("w") as log:
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    (out / "harness-result.json").write_text(
        json.dumps({"exit": result.returncode}) + "\n"
    )
    if baseline["input_files"] != {
        name: digest(inputs / name) for name in baseline["input_files"]
    }:
        raise ValueError("read-only input snapshot changed")
    result.check_returncode()


if __name__ == "__main__":
    main()
