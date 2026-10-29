"""Rehearse the full Run/Sandbox chain against an isolated HTTP sparse registry.

Inputs contain product snapshots, standalone probes and a prepared crate archive.
No fork checkout is available. Cargo starts with an empty home. The registry
has no publication API. Every source mutation uses disposable copies and caches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import tomllib
from registry_support import (
    NAME,
    VERSION,
    check_lock,
    digest,
    index_entry,
    inventory,
    registry_manifest,
)


def main() -> None:
    """Retain exact graphs, downloads, commands, fault witnesses and restoration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux":
        raise RuntimeError("runtime qualification requires native Linux")
    inputs, out = args.inputs.resolve(strict=True), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    workspace = Path("/workspace")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(word in key for word in ("TOKEN", "SECRET", "PASSWORD"))
        and not key.startswith(("MAD_", "CARGO_"))
        and key != "RUSTC_WRAPPER"
    }
    record = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "uid": os.getuid(),
        "commands": [],
        "registry_requests": [],
    }

    def save() -> None:
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")

    def run(
        label: str,
        argv: list,
        *,
        cwd: Path,
        environment: dict,
        succeeds=True,
        machine=False,
        timeout=1200,
    ) -> str:
        """Require runtime exit evidence; compilation failure cannot kill a fault."""
        print(label, flush=True)
        with (out / (label + ".log")).open("w") as log:
            result = subprocess.run(
                list(map(str, argv)),
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE if machine else log,
                stderr=log if machine else subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
            if machine:
                log.write(result.stdout)
                (out / (label + ".json")).write_text(result.stdout)
        record["commands"].append(
            {
                "label": label,
                "argv": list(map(str, argv)),
                "cwd": str(cwd),
                "exit": result.returncode,
                "expected_success": succeeds,
            }
        )
        save()
        if (result.returncode == 0) != succeeds:
            raise RuntimeError(
                f"{label}: unexpected exit {result.returncode}; inspect log"
            )
        return result.stdout if machine else (out / (label + ".log")).read_text()

    def clean_target(label: str, cwd: Path) -> None:
        """Release completed build stages without deleting their logs or inputs."""
        target = out / "targets" / label
        if (target / "CACHEDIR.TAG").exists():
            run(
                f"clean-{label}-{len(record.get('cleaned_targets', []))}",
                ["cargo", "clean", "--locked", "--target-dir", target],
                cwd=cwd,
                environment=environment(label),
            )
            record.setdefault("cleaned_targets", []).append(label)
            save()

    server = None
    thread = None
    target_roots: dict[str, Path] = {}
    try:
        baseline = json.loads((inputs / "BASELINE.json").read_text())
        for name, expected in baseline["input_files"].items():
            if digest(inputs / name) != expected:
                raise ValueError(f"input checksum mismatch: {name}")
        if (workspace / "mad-hakoniwa").exists() or (inputs / "mad-hakoniwa").exists():
            raise ValueError("fork checkout is available to the consumer")
        for name in ("mad-run", "mad-sandbox"):
            destination = workspace / name
            if destination.exists():
                destination.rmdir()
            shutil.copytree(inputs / name, destination)
            if (destination / "vendor").exists():
                raise ValueError("vendor archive must not enter this replay")
        sandbox, run_root = workspace / "mad-sandbox", workspace / "mad-run"
        target_roots.update({"mad-sandbox": sandbox, "mad-run": run_root})
        original_lockfiles = {
            repo: (repo / "Cargo.lock").read_text() for repo in (sandbox, run_root)
        }
        manifest_path = sandbox / "crates/mad-sandbox/Cargo.toml"
        manifest_path.write_text(registry_manifest(manifest_path.read_text()))
        archive = inputs / f"{NAME}-{VERSION}.crate"
        data = archive.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        if checksum != baseline["archive_sha256"]:
            raise ValueError("archive differs from host baseline")
        with tarfile.open(archive) as package:
            prefix = f"{NAME}-{VERSION}/"
            archive_files = {
                member.name.removeprefix(prefix): package.extractfile(member).read()
                for member in package.getmembers()
                if member.isfile()
            }
        manifest = tomllib.loads(archive_files["Cargo.toml"].decode())
        entry = index_entry(manifest, checksum)
        damaged = False

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                record["registry_requests"].append(self.path)
                if self.path == "/index/config.json":
                    payload = json.dumps(
                        {"dl": address + "/crates/{crate}/{version}/download"}
                    ).encode()
                elif self.path == "/index/ma/d-/mad-hakoniwa":
                    payload = (json.dumps(entry) + "\n").encode()
                elif self.path == f"/crates/{NAME}/{VERSION}/download":
                    payload = data[:-1] + bytes([data[-1] ^ 1]) if damaged else data
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:
                self.send_error(405, "review registry has no publication API")

            def log_message(self, format: str, *args) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        address = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        registry = "sparse+" + address + "/index/"
        home = out / "clean-cargo-home"
        home.mkdir()
        if list(home.iterdir()):
            raise ValueError("Cargo home is not empty")
        record["cargo_home_initially_empty"] = True
        (home / "config.toml").write_text(
            "[registries.review]\nindex = " + json.dumps(registry) + "\n"
        )

        def environment(label: str) -> dict:
            return {
                **env,
                "CARGO_HOME": str(home),
                "CARGO_TARGET_DIR": str(out / "targets" / label),
                "CARGO_INCREMENTAL": "0",
                "CARGO_PROFILE_DEV_DEBUG": "0",
                "CARGO_PROFILE_TEST_DEBUG": "0",
            }

        graphs = {}
        for repo in (sandbox, run_root):
            raw = run(
                repo.name + "-metadata",
                ["cargo", "metadata", "--format-version", "1"],
                cwd=repo,
                environment=environment(repo.name),
                machine=True,
            )
            graph = json.loads(raw)
            selected = [p for p in graph["packages"] if p["name"] == NAME]
            if len(selected) != 1 or any(
                p["name"] == "hakoniwa" for p in graph["packages"]
            ):
                raise ValueError(
                    "expected exactly one renamed fork and no original package"
                )
            fork = selected[0]
            source = Path(fork["manifest_path"]).parent.resolve(strict=True)
            if (
                fork["version"] != VERSION
                or fork["source"] not in {registry, "registry+" + registry}
                or not source.is_relative_to(home / "registry/src")
            ):
                raise ValueError("Cargo did not resolve the exact registry fork")
            check_lock(
                original_lockfiles[repo],
                (repo / "Cargo.lock").read_text(),
                registry,
                checksum,
            )
            graphs[repo.name] = {
                "id": fork["id"],
                "source": fork["source"],
                "version": fork["version"],
                "manifest_path": fork["manifest_path"],
                "checksum": checksum,
            }
            (out / (repo.name + "-Cargo.lock")).write_bytes(
                (repo / "Cargo.lock").read_bytes()
            )
        if graphs["mad-run"] != graphs["mad-sandbox"]:
            raise ValueError("product workspaces selected different fork packages")
        package_root = Path(graphs["mad-run"]["manifest_path"]).parent
        for name, expected in archive_files.items():
            if (package_root / name).read_bytes() != expected:
                raise ValueError(f"cached package differs from archive: {name}")
        original_package = inventory(package_root)
        record.update(
            {
                "graphs": graphs,
                "archive_sha256": checksum,
                "registry": registry,
                "fork_checkout_absent": True,
                "vendor_absent": True,
                "unrelated_locked_entries_unchanged": True,
            }
        )
        products_before = {
            str(repo): {
                str(path.relative_to(repo)): digest(path)
                for path in repo.rglob("*")
                if path.is_file()
            }
            for repo in (sandbox, run_root)
        }
        save()
        for repo in (sandbox, run_root):
            label, work_env = repo.name, environment(repo.name)
            run(
                label + "-provenance"
                if repo == sandbox
                else label + "-source-identity",
                ["python3", "tools/check-vendor.py"]
                if repo == sandbox
                else [
                    "python3",
                    "-c",
                    "import json; from tools.native_assets import source_hashes; print(json.dumps(source_hashes(), sort_keys=True))",
                ],
                cwd=repo,
                environment=work_env,
                machine=repo == run_root,
            )
            run(
                label + "-tool-tests",
                ["python3", "-m", "unittest", "discover", "-s", "tools/tests", "-v"],
                cwd=repo,
                environment=work_env,
            )
            features = ["--all-features"] if repo == run_root else []
            run(
                label + "-bins",
                ["cargo", "build", "--locked", "--workspace", *features, "--bins"],
                cwd=repo,
                environment=work_env,
            )
            if repo == run_root:
                run(
                    "run-worker",
                    [
                        "cargo",
                        "build",
                        "--locked",
                        "--manifest-path",
                        sandbox / "Cargo.toml",
                        "-p",
                        "mad-sandbox-worker",
                    ],
                    cwd=repo,
                    environment=work_env,
                )
            run(
                label + "-tests",
                [
                    "cargo",
                    "test",
                    "--locked",
                    "--workspace",
                    *features,
                    "--all-targets",
                ],
                cwd=repo,
                environment=work_env,
            )
            run(
                label + "-doctests",
                ["cargo", "test", "--locked", "--workspace", *features, "--doc"],
                cwd=repo,
                environment=work_env,
            )
            run(
                label + "-clippy",
                [
                    "cargo",
                    "clippy",
                    "--locked",
                    "--workspace",
                    *features,
                    "--all-targets",
                    "--",
                    "-D",
                    "warnings",
                ],
                cwd=repo,
                environment=work_env,
            )
        identities = json.loads((out / "mad-run-source-identity.json").read_text())
        expected_identity = {
            "dependencies/" + NAME + "/" + name: digest(path)
            for pattern in manifest["package"]["include"]
            for path in package_root.glob(pattern)
            if path.is_file()
            for name in [str(path.relative_to(package_root))]
        }
        expected_identity["dependencies/" + NAME + "/Cargo.toml"] = digest(
            package_root / "Cargo.toml"
        )
        actual_identity = {
            name: value
            for name, value in identities.items()
            if name.startswith("dependencies/")
        }
        if actual_identity != expected_identity:
            raise ValueError(
                "Run build identity does not describe the registry package inputs"
            )
        record["registry_source_identity"] = "passed"
        run(
            "rust-bundles",
            ["python3", "-m", "tools.verify_rust_bundle"],
            cwd=run_root,
            environment=environment(run_root.name),
            timeout=1800,
        )
        run(
            "installed-runtime",
            ["python3", "-m", "tools.verify_installed_runtime"],
            cwd=run_root,
            environment=environment(run_root.name),
        )

        clean_target("mad-run", run_root)

        consumer = workspace / "registry-probe"
        target_roots["consumer"] = consumer
        shutil.copytree(inputs / "registry-probe", consumer)
        (consumer / "tests").mkdir()
        for path in sorted((inputs / "upstream-tests").rglob("*.rs")):
            shutil.copy2(path, consumer / "tests" / path.name)
        (consumer / "Cargo.toml").write_text(f'''[package]
name = "hakoniwa-registry-probe"
version = "0.1.0"
edition = "2024"
[dependencies]
hakoniwa = {{ package = "{NAME}", version = "={VERSION}", registry = "review", features = ["landlock"] }}
[dev-dependencies]
libc = "0.2.186"
tempfile = "3.27.0"
''')
        consumer_env = environment("consumer")
        run(
            "consumer-lock",
            ["cargo", "generate-lockfile", "--offline"],
            cwd=consumer,
            environment=consumer_env,
        )
        run(
            "consumer-bins",
            ["cargo", "build", "--locked", "--bins"],
            cwd=consumer,
            environment=consumer_env,
        )
        run(
            "consumer-run",
            ["cargo", "run", "--locked", "--bin", "hakoniwa-registry-probe"],
            cwd=consumer,
            environment=consumer_env,
        )
        run(
            "consumer-repairs",
            ["cargo", "test", "--locked", "--tests", "--", "--nocapture"],
            cwd=consumer,
            environment=consumer_env,
        )
        run(
            "consumer-supervisor-image",
            [
                "cargo",
                "test",
                "--locked",
                "--test",
                "supervisor_repair",
                "--",
                "--ignored",
                "--nocapture",
            ],
            cwd=consumer,
            environment={
                **consumer_env,
                "HAKONIWA_TEST_SUPERVISOR": str(
                    out / "targets/consumer/debug/supervisor"
                ),
            },
        )
        run(
            "consumer-termination-image",
            ["cargo", "test", "--locked", "--test", "termination_repair", "--", "--nocapture"],
            cwd=consumer,
            environment={
                **consumer_env,
                "HAKONIWA_TEST_SUPERVISOR": str(out / "targets/consumer/debug/supervisor"),
            },
        )
        run(
            "consumer-overlays",
            [
                "cargo",
                "test",
                "--locked",
                "--test",
                "overlay_repair",
                "--",
                "--ignored",
                "--nocapture",
            ],
            cwd=consumer,
            environment={
                **consumer_env,
                "HAKONIWA_TEST_SUPERVISOR": str(
                    out / "targets/consumer/debug/supervisor"
                ),
            },
        )
        clean_target("consumer", consumer)
        for label, script, marker, count in (
            ("startup-faults", "check-linux-startup.py", "STARTUP_FAULT_REAPED", 8),
            (
                "boundary-faults",
                "check-security-boundaries.py",
                "SECURITY_FAULT_REJECTED",
                13,
            ),
            (
                "owner-faults",
                "check-linux-captured-owner.py",
                "CAPTURED_OWNER_FAULT_REJECTED",
                6,
            ),
        ):
            output = run(
                label,
                ["python3", "tools/" + script],
                cwd=sandbox,
                environment=environment(sandbox.name),
                timeout=2400,
            )
            if output.count(marker) != count:
                raise ValueError(f"{label}: missing intended runtime witnesses")
            record[label] = count
        if inventory(package_root) != original_package:
            raise ValueError("instrumented registry source was not restored")
        for repo in (sandbox, run_root):
            for name, expected in products_before[str(repo)].items():
                if digest(repo / name) != expected:
                    raise ValueError(f"product source was not restored: {repo / name}")
            check_lock(
                original_lockfiles[repo],
                (repo / "Cargo.lock").read_text(),
                registry,
                checksum,
            )
        run(
            "restored-provenance",
            ["python3", "tools/check-vendor.py"],
            cwd=sandbox,
            environment=environment(sandbox.name),
        )
        record["source_restored"] = True
        clean_target("mad-sandbox", sandbox)
        damaged = True
        negative = out / "negative-cargo-home"
        negative.mkdir()
        (negative / "config.toml").write_bytes((home / "config.toml").read_bytes())
        failure = run(
            "bad-checksum",
            ["cargo", "fetch", "--locked"],
            cwd=run_root,
            environment={**environment(run_root.name), "CARGO_HOME": str(negative)},
            succeeds=False,
        )
        if "checksum" not in failure.lower() or NAME not in failure:
            raise ValueError("damaged archive failed for an unrelated reason")
        if record["registry_requests"].count(f"/crates/{NAME}/{VERSION}/download") < 2:
            raise ValueError("registry download receipts missing")
        record["damaged_archive_refused"] = True
        record["status"] = "passed"
    except Exception as error:
        record["failure"] = str(error)
        record["status"] = "failed"
        raise
    finally:
        cleanup_errors = []
        for label, root in target_roots.items():
            try:
                clean_target(label, root)
            except Exception as error:
                cleanup_errors.append(f"{label}: {error}")
        record["cargo_targets_cleaned"] = not cleanup_errors
        if cleanup_errors:
            record.update(status="failed", cleanup_errors=cleanup_errors)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"status": record["status"], "out": str(out)}), flush=True)
        if cleanup_errors:
            raise RuntimeError("registry target cleanup failed: " + "; ".join(cleanup_errors))


if __name__ == "__main__":
    main()
