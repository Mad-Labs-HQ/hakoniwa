# Qualification tools

These tools verify the library and prepare disposable integration runs. They do
not publish crates, push branches or submit upstream changes.

## Source provenance

Run from the repository root with its declared environment:

```sh
python -m tools.verify_provenance
```

This checks the package identity, publication guard, original license and
reversible source patch. It needs no internal reports or evidence directory.
For a qualified source inventory or exported patch series, pass those records
explicitly:

```sh
python -m tools.verify_provenance \
  --source-inventory /path/to/PORTED-SOURCE.json \
  --patch-series /path/to/SERIES.json
```

Repeat `--patch-series` to verify more than one series.

## Registry integration

The integration lane requires sibling Mad Run and Mad Sandbox checkouts and the
prepared native ARM64 lab image. It freezes source inputs, packages the crate
and tests consumption without a fork checkout or vendor tree. Qualification
records are explicit inputs rather than files assumed to exist in this clone.

```sh
python -m tools.run_registry \
  --source-inventory /path/to/PORTED-SOURCE.json \
  --patch-series /path/to/SERIES.json \
  --out /path/to/new-run
```

Add `--prepare-only` to verify the package and frozen inputs without starting a
runtime test. This is a preparation check, not native qualification.

The Linux entrypoint uses the copied harness and archive. It runs workspace
checks, relocated bundles, the installer, focused library tests and compiled
fault probes. This lane still targets the existing ARM64 lab. Native x86-64
and hosted CI remain separate work.

## Permanent tests

The repair regressions live in `hakoniwa/tests/`:

- `ownership_repair.rs`
- `termination_repair.rs`
- `remount_repair.rs`
- `supervisor_repair.rs`
- `overlay_repair.rs`

Image tests require a helper built from the same library and feature set:

```sh
cargo build --locked -p mad-hakoniwa --features landlock \
  --example repair_supervisor --target-dir target/repair-tests
HAKONIWA_TEST_SUPERVISOR="$PWD/target/repair-tests/debug/examples/repair_supervisor" \
  cargo test --locked -p mad-hakoniwa --features landlock \
  --target-dir target/repair-tests \
  --test supervisor_repair --test overlay_repair -- --ignored --nocapture
```

The registry producer copies those canonical tests and the supervisor example
into its disposable consumer. `tools/probes/registry-consumer/` supplies the
standalone registry-consumer program.

`upgrade_stages.py` replays supplied vanilla source and incremental patches.
`upgrade_overlay_fault.py` challenges mount-data serialization in that disposable
stage workspace, rebuilds the helper and checks restoration.

Run tooling tests with:

```sh
python -m unittest discover -s tools/tests -v
```

## Internal records

Reports, ledgers, archived crates, historical drivers and exact test receipts
belong in `docs/local/`. They are not inputs to the basic provenance check.
Frozen evidence retains the paths and commands used at execution time.
