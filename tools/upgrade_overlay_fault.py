"""Falsify omission of 1.8.0 mount data from the image-supervisor frame.

Uses the disposable stage workspace. The helper is rebuilt from each source
state, so build-fingerprint refusal cannot substitute for the mount assertion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    stage, out = args.stage.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = stage / "source"
    path = source / "hakoniwa/src/unshare/newns/mount.rs"
    original = path.read_bytes()
    anchor = "    pub(crate) data: Option<String>,"
    if original.decode().count(anchor) != 1:
        raise ValueError("mount-data fault anchor drifted")
    env = {
        **os.environ,
        "CARGO_HOME": str(stage / "cargo-home"),
        "CARGO_TARGET_DIR": str(stage / "target"),
        "HAKONIWA_TEST_SUPERVISOR": str(stage / "target/debug/upgrade-supervisor"),
    }
    record = {
        "status": "running",
        "commands": [],
        "original_sha256": hashlib.sha256(original).hexdigest(),
    }

    def run(label: str, argv: list, *, expected=0) -> str:
        print(label, flush=True)
        with (out / (label + ".log")).open("w") as log:
            result = subprocess.run(
                list(map(str, argv)),
                cwd=source,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
        record["commands"].append(
            {
                "label": label,
                "argv": list(map(str, argv)),
                "exit": result.returncode,
                "expected": expected,
            }
        )
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        if result.returncode != expected:
            raise ValueError(f"{label} missed its expected exit")
        return (out / (label + ".log")).read_text()

    helper = [
        "cargo",
        "build",
        "--locked",
        "--manifest-path",
        stage / "helper/Cargo.toml",
    ]
    test = [
        "cargo",
        "test",
        "--locked",
        "-p",
        "hakoniwa",
        "--features",
        "landlock",
        "--test",
        "overlay_repair",
    ]
    try:
        path.write_text(
            original.decode().replace(anchor, "    #[serde(skip)]\n" + anchor)
        )
        run("mutant-helper", helper)
        run("mutant-compiles", [*test, "--no-run"])
        output = run(
            "mutant-rejected",
            [
                *test,
                "image_preserves_read_only_overlay_data",
                "--",
                "--exact",
                "--ignored",
                "--nocapture",
            ],
            expected=101,
        )
        if (
            "image_preserves_read_only_overlay_data ... FAILED" not in output
            or "None" not in output
            or "mount(" not in output
        ):
            raise ValueError(
                "omitted mount data did not reach the intended runtime assertion"
            )
        record["fault_rejected"] = True
    finally:
        path.write_bytes(original)
        if path.read_bytes() != original:
            raise ValueError("mount source not restored")
        record["source_restored"] = True
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    run("restored-helper", helper)
    run("restored-overlays", [*test, "--", "--ignored", "--nocapture"])
    record["status"] = "passed"
    (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
