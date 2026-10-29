"""Run vanilla 1.8.0 and each incremental repair in a disposable Linux tree.

Only the supplied source snapshot and patches are read. The selected native
controls avoid Alpine fixture assumptions and keep stdin open where required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inputs, out = args.inputs.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "source"
    shutil.copytree(inputs / "source", source)
    home = out / "cargo-home"
    home.mkdir()
    env = {
        **os.environ,
        "CARGO_HOME": str(home),
        "CARGO_TARGET_DIR": str(out / "target"),
    }
    record = {
        "status": "running",
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "uid": os.getuid(),
        "commands": [],
    }

    def save() -> None:
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")

    def run(
        label: str, argv: list, *, cwd=source, hold_stdin=False, extra=None
    ) -> None:
        print(label, flush=True)
        with ExitStack() as resources, (out / (label + ".log")).open("w") as log:
            stream = None
            if hold_stdin:
                reader, writer = os.pipe()
                stream = resources.enter_context(os.fdopen(reader, "rb"))
                resources.enter_context(os.fdopen(writer, "wb"))
            result = subprocess.run(
                list(map(str, argv)),
                cwd=cwd,
                env={**env, **(extra or {})},
                stdin=stream,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
        record["commands"].append(
            {"label": label, "argv": list(map(str, argv)), "exit": result.returncode}
        )
        save()
        result.check_returncode()

    try:
        run("rust-version", ["rustc", "--version"])
        run(
            "vanilla-tests",
            [
                "cargo",
                "test",
                "-p",
                "hakoniwa",
                "--features",
                "landlock",
                "--test",
                "child_test",
                "--test",
                "command_test",
                "--",
                "--nocapture",
            ],
            hold_stdin=True,
        )
        series = json.loads((inputs / "patches/SERIES.json").read_text())
        for row in series["patches"]:
            patch = inputs / "patches" / (row["label"] + ".patch")
            if hashlib.sha256(patch.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("patch hash differs from reviewed series")
            run(row["label"] + "-apply", ["git", "apply", patch])
            run(
                row["label"] + "-check",
                ["cargo", "check", "-p", "hakoniwa", "--features", "landlock"],
            )
            tests = {
                "01-pinned-child-ownership": "ownership_repair",
                "02-termination-evidence": "termination_repair",
                "03-read-only-remount": "remount_repair",
            }
            if row["label"] in tests:
                run(
                    row["label"] + "-test",
                    [
                        "cargo",
                        "test",
                        "--locked",
                        "-p",
                        "hakoniwa",
                        "--features",
                        "landlock",
                        "--test",
                        tests[row["label"]],
                        "--",
                        "--nocapture",
                    ],
                )
        run(
            "repaired-tests",
            [
                "cargo",
                "test",
                "--locked",
                "-p",
                "hakoniwa",
                "--features",
                "landlock",
                "--test",
                "child_test",
                "--test",
                "command_test",
                "--test",
                "ownership_repair",
                "--test",
                "termination_repair",
                "--test",
                "remount_repair",
                "--",
                "--nocapture",
            ],
            hold_stdin=True,
        )
        helper = out / "helper"
        (helper / "src").mkdir(parents=True)
        (helper / "Cargo.toml").write_text(
            '[package]\nname="upgrade-supervisor"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nhakoniwa={path='
            + json.dumps(str(source / "hakoniwa"))
            + ',features=["landlock"]}\n'
        )
        shutil.copy2(inputs / "supervisor.rs", helper / "src/main.rs")
        run("image-helper", ["cargo", "build"], cwd=helper)
        for test in ("supervisor_repair", "overlay_repair"):
            run(
                test,
                [
                    "cargo",
                    "test",
                    "--locked",
                    "-p",
                    "hakoniwa",
                    "--features",
                    "landlock",
                    "--test",
                    test,
                    "--",
                    "--ignored",
                    "--nocapture",
                ],
                extra={
                    "HAKONIWA_TEST_SUPERVISOR": str(
                        out / "target/debug/upgrade-supervisor"
                    )
                },
            )
        record["status"] = "passed"
    except Exception as error:
        record["status"] = "failed"
        record["failure"] = str(error)
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
