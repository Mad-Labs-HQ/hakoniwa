"""Qualify failed-startup cleanup in both native supervisor modes.

Run from the repository root on Linux. The library, tests and helper use one
explicit feature set and Cargo target. Evidence is separate from source.
This tool does not publish, push, merge or submit changes.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Require truthful polling, reaping and retained authority in each mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--features", required=True, choices=["all", "landlock"])
    parser.add_argument("--arch", required=True, choices=["x86_64", "aarch64"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != args.arch:
        raise RuntimeError("qualification requires the selected native Linux architecture")
    root = Path.cwd()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    feature_flags = ["--all-features"] if args.features == "all" else ["--features", "landlock"]
    common = ["--locked", "-p", args.package, *feature_flags]
    environment = {
        **os.environ,
        "CARGO_INCREMENTAL": "0",
        "CARGO_TARGET_DIR": str(output / "target"),
        "TMPDIR": str(output / "temporary"),
    }
    Path(environment["TMPDIR"]).mkdir()
    environment.pop("HAKONIWA_TEST_SUPERVISOR", None)
    result = {"status": "running", "architecture": args.arch, "package": args.package,
              "features": args.features, "commands": []}

    def save() -> None:
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(label: str, command: list[str], extra: dict[str, str] | None = None) -> str:
        """Keep complete command output and propagate any failed native check."""
        print(label, flush=True)
        with (output / f"{label}.log").open("w") as log:
            completed = subprocess.run(command, cwd=root, env={**environment, **(extra or {})},
                                       stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=600, check=False)
        result["commands"].append({"label": label, "argv": command, "exit": completed.returncode})
        save()
        completed.check_returncode()
        return (output / f"{label}.log").read_text()

    try:
        run("format", ["cargo", "fmt", "--all", "--", "--check"])
        run("clippy", ["cargo", "clippy", *common, "--all-targets", "--", "-D", "warnings"])
        run("build-supervisor", ["cargo", "build", *common, "--example", "repair_supervisor"])
        text = run("compile-reaping", ["cargo", "test", *common, "--test", "setup_reaping_test",
                                      "--no-run", "--message-format=json"])
        artifacts = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
        binaries = [item["executable"] for item in artifacts
                    if item.get("reason") == "compiler-artifact" and item.get("executable")]
        binary, = binaries
        run("library-unit-tests", ["cargo", "test", *common, "--lib", "--", "--nocapture"])
        helper = str(output / "target/debug/examples/repair_supervisor")
        for mode in ["fork", "image"]:
            mode_env = {} if mode == "fork" else {"HAKONIWA_TEST_SUPERVISOR": helper}
            run(f"{mode}-setup-reaping", ["cargo", "test", *common,
                "--test", "setup_reaping_test", "--", "--nocapture"], mode_env)
            for error in [1, 38]:
                run(f"{mode}-refused-pidfd-{error}", [sys.executable,
                    str(root / "tools/refuse_syscall.py"), "pidfd_open", str(error), binary,
                    "shared::refused_acquisition_must_reap_before_wait_returns",
                    "--exact", "--ignored", "--nocapture"],
                    {**mode_env, "HAKONIWA_PIDFD_REFUSAL": str(error)})
        run("image-and-overlay-controls", ["cargo", "test", *common,
            "--test", "supervisor_repair", "--test", "overlay_repair",
            "--", "--ignored", "--nocapture"], {"HAKONIWA_TEST_SUPERVISOR": helper})
        result["status"] = "passed"
    except Exception as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        try:
            if (output / "target/CACHEDIR.TAG").exists():
                run("cargo-clean", ["cargo", "clean"])
                result["cargo_target_cleaned"] = True
        except Exception as error:
            result.update(status="failed", cleanup_error=str(error))
            raise
        finally:
            save()


if __name__ == "__main__":
    main()
