"""Qualify an exact ownership commit against its pinned upstream baseline.

Requires a native Linux runner with namespace support and a checkout containing
both revisions. Outputs logs outside source trees and cleans each Cargo target.
The workflow that calls this runner is fork-only qualification infrastructure.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


def digest(path: Path) -> str:
    """Record bytes independently of compiler and Cargo caches."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Require failing controls, passing repaired tests and rejected ablations."""
    candidate, baseline, destination, expected_arch = sys.argv[1:]
    if platform.system() != "Linux" or platform.machine() != expected_arch:
        raise RuntimeError("qualification requires the requested native architecture")
    checkout = Path.cwd()
    output = Path(destination).resolve()
    output.mkdir(parents=True, exist_ok=False)
    roots = {lane: output / lane for lane in ("baseline", "candidate")}
    for lane, revision in (("baseline", baseline), ("candidate", candidate)):
        archive = subprocess.check_output(["git", "archive", revision])
        roots[lane].mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(roots[lane], filter="data")
    for name in ("ownership_parity_test.rs", "support/ownership_parity.rs"):
        target = roots["baseline"] / "hakoniwa/tests" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(roots["candidate"] / "hakoniwa/tests" / name, target)
    source_hashes = {
        str(path.relative_to(roots["candidate"])): digest(path)
        for path in (roots["candidate"] / "hakoniwa").rglob("*.rs")
    }
    locks = {lane: digest(root / "Cargo.lock") for lane, root in roots.items()}
    result = {
        "status": "running",
        "candidate": candidate,
        "baseline": baseline,
        "qualification_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "architecture": platform.machine(),
        "commands": [],
        "cleaned_targets": [],
        "shared_regression_sha256": {
            lane: digest(root / "hakoniwa/tests/support/ownership_parity.rs")
            for lane, root in roots.items()
        },
    }
    if len(set(result["shared_regression_sha256"].values())) != 1:
        raise AssertionError("baseline and candidate regression bodies differ")

    def save() -> None:
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def environment(lane: str) -> dict[str, str]:
        temporary = output / "temporary" / lane
        temporary.mkdir(parents=True, exist_ok=True)
        return {
            **os.environ,
            "CARGO_TARGET_DIR": str(output / "targets" / lane),
            "CARGO_INCREMENTAL": "0",
            "TMPDIR": str(temporary),
        }

    def run(label: str, lane: str, argv: list[str], failure: str | None = None) -> None:
        """Accept negative cases only at their intended runtime assertion."""
        print(label, flush=True)
        with (output / f"{label}.log").open("w") as log:
            completed = subprocess.run(
                argv,
                cwd=roots[lane],
                env=environment(lane),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
                check=False,
            )
        result["commands"].append(
            {"label": label, "lane": lane, "argv": argv,
             "exit": completed.returncode, "expected_runtime_failure": failure}
        )
        save()
        if failure is None:
            completed.check_returncode()
        elif completed.returncode != 101 or failure not in (output / f"{label}.log").read_text():
            raise AssertionError(f"{label}: intended runtime assertion missing")

    def tests(*arguments: str) -> list[str]:
        return ["cargo", "test", "--locked", "-p", "hakoniwa", "--all-features", *arguments]

    def clean(lane: str) -> None:
        target = output / "targets" / lane
        if (target / "CACHEDIR.TAG").exists():
            run(f"{lane}-cargo-clean", lane, ["cargo", "clean"])
            result["cleaned_targets"].append(lane)
            save()

    child = roots["candidate"] / "hakoniwa/src/child.rs"
    original = child.read_bytes()
    try:
        run("baseline-compile", "baseline", tests("--test", "ownership_parity_test", "--no-run"))
        cases = [
            ("parent_death_signal_is_a_live_control", None),
            ("kill_survives_cleared_parent_death_signal", "Child::kill left the workload alive"),
            ("rootfs_remains_owned_until_child_drop", "wait disposed the still-owned rootfs"),
        ]
        for name, failure in cases:
            run(f"baseline-{name}", "baseline", tests(
                "--test", "ownership_parity_test", f"shared::{name}",
                "--", "--exact", "--nocapture"), failure)
        clean("baseline")
        run("candidate-format", "candidate", ["cargo", "fmt", "--all", "--", "--check"])
        run("candidate-clippy", "candidate", [
            "cargo", "clippy", "--locked", "-p", "hakoniwa", "--all-features",
            "--lib", "--test", "ownership_repair", "--test", "ownership_parity_test",
            "--", "-D", "warnings",
        ])
        run("candidate-all-tests", "candidate", tests("--all-targets", "--", "--nocapture"))
        run("candidate-doctests", "candidate", tests("--doc", "--", "--nocapture"))
        for iteration in range(5):
            run(f"candidate-parallel-{iteration}", "candidate", tests(
                "--test", "ownership_parity_test", "--", "--test-threads=4", "--nocapture"))
        cancellation = original.decode().replace(
            "self.inner_pidfd() {", "self.inner_pidfd().filter(|_| false) {")
        if cancellation == original.decode():
            raise AssertionError("cancellation ablation did not alter source")
        child.write_text(cancellation)
        run("candidate-cancellation-ablated", "candidate", tests(
            "--test", "ownership_parity_test", "shared::kill_survives_cleared_parent_death_signal",
            "--", "--exact", "--nocapture"), "Child::kill left the workload alive")
        child.write_bytes(original)
        retention = original.decode().replace(
            "        self.logging();\n", "        self.logging();\n        drop(self._tmpdir.take());\n", 1)
        if retention == original.decode():
            raise AssertionError("rootfs ablation did not alter source")
        child.write_text(retention)
        run("candidate-retention-ablated", "candidate", tests(
            "--test", "ownership_parity_test", "shared::rootfs_remains_owned_until_child_drop",
            "--", "--exact", "--nocapture"), "wait disposed the still-owned rootfs")
        child.write_bytes(original)
        run("candidate-restored", "candidate", tests(
            "--test", "ownership_parity_test", "--", "--test-threads=4", "--nocapture"))
        for name, expected in source_hashes.items():
            if digest(roots["candidate"] / name) != expected:
                raise AssertionError(f"candidate source not restored: {name}")
        if any(digest(root / "Cargo.lock") != locks[lane] for lane, root in roots.items()):
            raise AssertionError("a source lockfile changed")
        result.update(status="passed", candidate_source_restored=True, lockfiles_unchanged=True)
    except Exception as error:
        result.update(status="failed", failure=str(error))
        raise
    finally:
        child.write_bytes(original)
        cleanup_errors = []
        for lane in roots:
            try:
                clean(lane)
            except Exception as error:
                cleanup_errors.append(f"{lane}: {error}")
        if cleanup_errors:
            result.update(status="failed", cleanup_failures=cleanup_errors)
        save()
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors))
    if Path.cwd() != checkout:
        raise AssertionError("qualification changed the caller's working directory")


if __name__ == "__main__":
    main()
