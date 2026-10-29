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
    reaping_baseline = "58f201cc00ebdd0b6684f865264ce95c0bda13b7"
    report_baseline = "3be907c21124c76b7bca786af2ec4b534259d924"
    roots = {lane: output / lane for lane in ("baseline", "reaping-baseline", "report-baseline", "candidate")}
    for lane, revision in (("baseline", baseline), ("reaping-baseline", reaping_baseline),
                           ("report-baseline", report_baseline), ("candidate", candidate)):
        archive = subprocess.check_output(["git", "archive", revision])
        roots[lane].mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            # These pinned Git trees contain guest-absolute BusyBox fixture links.
            source.extractall(roots[lane], filter="fully_trusted")
    for name in ("ownership_parity_test.rs", "support/ownership_parity.rs"):
        target = roots["baseline"] / "hakoniwa/tests" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(roots["candidate"] / "hakoniwa/tests" / name, target)
    for name in ("setup_reaping_test.rs", "support/setup_reaping.rs"):
        target = roots["reaping-baseline"] / "hakoniwa/tests" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(roots["candidate"] / "hakoniwa/tests" / name, target)
    with (roots["report-baseline"] / "hakoniwa/src/child/tests.rs").open("a") as regression:
        regression.write('''
#[test]
fn report_reaping_before_repair() -> std::io::Result<()> {
    let mut probe = PendingFailure::new()?;
    probe.child.state = ChildState::Running;
    probe.child.status_reader_noleading = true;
    drop(probe.gate.take());
    assert!(probe.child.wait().is_err());
    probe.assert_reaped();
    assert!(!matches!(probe.child.state, ChildState::Running | ChildState::SetupFailed(_)),
        "REPORT_ERROR_LOST_KERNEL_REAPING");
    Ok(())
}
''')
    source_hashes = {
        str(path.relative_to(roots["candidate"])): digest(path)
        for path in (roots["candidate"] / "hakoniwa").rglob("*.rs")
    }
    locks = {lane: digest(root / "Cargo.lock") for lane, root in roots.items()}
    result = {
        "status": "running",
        "candidate": candidate,
        "baseline": baseline,
        "reaping_baseline": reaping_baseline,
        "report_baseline": report_baseline,
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
        "shared_reaping_sha256": {
            lane: digest(roots[lane] / "hakoniwa/tests/support/setup_reaping.rs")
            for lane in ("reaping-baseline", "candidate")
        },
    }
    if len(set(result["shared_regression_sha256"].values())) != 1:
        raise AssertionError("baseline and candidate regression bodies differ")
    if len(set(result["shared_reaping_sha256"].values())) != 1:
        raise AssertionError("baseline and candidate reaping regressions differ")

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

    def run(label: str, lane: str, argv: list[str], failure: str | None = None,
            extra: dict[str, str] | None = None) -> None:
        """Accept negative cases only at their intended runtime assertion."""
        print(label, flush=True)
        with (output / f"{label}.log").open("w") as log:
            completed = subprocess.run(
                argv,
                cwd=roots[lane],
                env={**environment(lane), **(extra or {})},
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
        else:
            text = (output / f"{label}.log").read_text()
            if completed.returncode != 101 or failure not in text or "test result: FAILED." not in text:
                raise AssertionError(f"{label}: intended runtime assertion missing")

    def tests(*arguments: str) -> list[str]:
        return ["cargo", "test", "--locked", "-p", "hakoniwa", "--all-features", *arguments]

    def clean(lane: str) -> None:
        target = output / "targets" / lane
        if (target / "CACHEDIR.TAG").exists():
            run(f"{lane}-cargo-clean", lane, ["cargo", "clean"])
            result["cleaned_targets"].append(lane)
            save()

    def reaping_binary(lane: str, label: str) -> str:
        run(label, lane, tests("--test", "setup_reaping_test", "--no-run", "--message-format=json"))
        artifacts = [json.loads(line) for line in (output / f"{label}.log").read_text().splitlines()
                     if line.startswith("{")]
        binary, = [row["executable"] for row in artifacts
                   if row.get("reason") == "compiler-artifact" and row.get("executable")]
        return binary

    def refused(lane: str, binary: str, prefix: str, failure: str | None = None) -> None:
        for error in [1, 38]:
            run(f"{prefix}-{error}", lane, [sys.executable, str(checkout / "tools/refuse_syscall.py"),
                "pidfd_open", str(error), binary,
                "shared::refused_acquisition_must_reap_before_wait_returns",
                "--exact", "--ignored", "--nocapture"], failure,
                {"HAKONIWA_PIDFD_REFUSAL": str(error)})

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
        previous = reaping_binary("reaping-baseline", "reaping-baseline-compile")
        refused("reaping-baseline", previous, "reaping-baseline-refusal",
                "cached pidfd acquisition failure returned from wait without reaping")
        clean("reaping-baseline")
        run("report-baseline-negative", "report-baseline", tests(
            "--lib", "report_reaping_before_repair", "--", "--nocapture"),
            "REPORT_ERROR_LOST_KERNEL_REAPING")
        clean("report-baseline")
        run("candidate-format", "candidate", ["cargo", "fmt", "--all", "--", "--check"])
        run("candidate-clippy", "candidate", [
            "cargo", "clippy", "--locked", "-p", "hakoniwa", "--all-features",
            "--lib", "--test", "ownership_repair", "--test", "ownership_parity_test",
            "--test", "setup_reaping_test",
            "--", "-D", "warnings",
        ])
        run("candidate-all-tests", "candidate", tests("--all-targets", "--", "--nocapture"))
        run("candidate-doctests", "candidate", tests("--doc", "--", "--nocapture"))
        current = reaping_binary("candidate", "candidate-reaping-compile")
        refused("candidate", current, "candidate-refusal")
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
            "        Self::logging(&status);\n", "        Self::logging(&status);\n        drop(self._tmpdir.take());\n", 1)
        if retention == original.decode():
            raise AssertionError("rootfs ablation did not alter source")
        child.write_text(retention)
        run("candidate-retention-ablated", "candidate", tests(
            "--test", "ownership_parity_test", "shared::rootfs_remains_owned_until_child_drop",
            "--", "--exact", "--nocapture"), "wait disposed the still-owned rootfs")
        child.write_bytes(original)
        run("candidate-restored", "candidate", tests(
            "--test", "ownership_parity_test", "--", "--test-threads=4", "--nocapture"))
        shortcut = original.decode()
        anchors = [
            ("pub fn try_wait(&mut self) -> Result<Option<ExitStatus>> {\n",
             "            return Ok(Some(status.clone()));\n"),
            ("pub fn wait(&mut self) -> Result<ExitStatus> {\n",
             "            return Ok(status.clone());\n"),
        ]
        for anchor, returned in anchors:
            if shortcut.count(anchor) != 1:
                raise AssertionError("cached reaping ablation anchor is ambiguous")
            shortcut = shortcut.replace(anchor, anchor +
                "        if let ChildState::SetupFailed(status) = &self.state {\n" +
                returned + "        }\n", 1)
        if shortcut == original.decode():
            raise AssertionError("reaping ablation did not alter source")
        child.write_text(shortcut)
        ablated = reaping_binary("candidate", "candidate-reaping-ablated-compile")
        refused("candidate", ablated, "candidate-reaping-ablated",
                "cached pidfd acquisition failure returned from wait without reaping")
        child.write_bytes(original)
        restored = reaping_binary("candidate", "candidate-reaping-restored-compile")
        refused("candidate", restored, "candidate-reaping-restored")
        marker = "        let status = report?;"
        if original.count(marker.encode()) != 1:
            raise AssertionError("report reaping ablation anchor is ambiguous")
        child.write_bytes(original.replace(marker.encode(),
            b"        if report.is_err() { self.state = ChildState::Running; }\n" + marker.encode()))
        run("candidate-report-state-ablated", "candidate", tests(
            "--lib", "child::tests::report_errors_preserve_reaping_truth", "--", "--exact", "--nocapture"),
            "ChildState::ReapedWithoutReport")
        child.write_bytes(original)
        marker = "if !matches!(self.state, ChildState::Running) {"
        if original.count(marker.encode()) != 1:
            raise AssertionError("numeric PID guard ablation anchor is ambiguous")
        child.write_bytes(original.replace(marker.encode(), b"if false {"))
        run("candidate-numeric-pid-guard-ablated", "candidate", tests(
            "--lib", "child::tests::report_error_prevents_numeric_pid_signal", "--", "--exact", "--nocapture"),
            "kill signaled an unrelated numeric PID")
        child.write_bytes(original)
        run("candidate-restored-unit-tests", "candidate", tests("--lib", "--", "--nocapture"))
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
