//! Modification notice: Mad Labs, Inc added this file; changes recorded through
//! 2026-10-28.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Fingerprints this hakoniwa build for supervisor frames: a supervisor
//! started from its own image refuses a frame from a host built from other
//! sources, manifest or features, whose frame layout may differ.
//!
//! Assumes the sources are the `.rs` files under `src/`, the manifest is
//! `Cargo.toml`, and the features Cargo enabled are in the `CARGO_FEATURE_*`
//! variables, as Cargo sets them for a build script. Dotfiles (an editor's
//! lock or swap file) and other files under `src/` are not sources.
//!
//! Gotcha: the hash is FNV-1a written out here, not `std`'s hasher, so two
//! builds of the same sources and features agree whatever compiler built
//! them. Any source change, a comment included, changes the fingerprint; a
//! running host and a rebuilt supervisor then refuse each other until the
//! host restarts, which is the safe side.

use std::path::{Path, PathBuf};

/// FNV-1a's 64-bit offset basis and prime.
const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

fn main() {
    let mut files = vec![PathBuf::from("Cargo.toml")];
    collect(Path::new("src"), &mut files);
    files.sort();
    let mut features = std::env::vars_os()
        .filter_map(|(key, _)| {
            key.to_str()?
                .strip_prefix("CARGO_FEATURE_")
                .map(str::to_owned)
        })
        .collect::<Vec<_>>();
    features.sort();

    let fingerprint = files
        .iter()
        .flat_map(|file| {
            let contents = std::fs::read(file)
                .unwrap_or_else(|e| panic!("cannot read {}: {e}", file.display()));
            [file.to_string_lossy().as_bytes().to_vec(), contents]
        })
        .chain(features.into_iter().map(String::into_bytes))
        .fold(FNV_OFFSET, |hash, bytes| {
            bytes.iter().fold(hash, |hash, byte| {
                (hash ^ u64::from(*byte)).wrapping_mul(FNV_PRIME)
            })
        });

    println!("cargo:rustc-env=HAKONIWA_FRAME_FINGERPRINT={fingerprint:016x}");
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=Cargo.toml");
}

/// Every `.rs` file under `dir`, recursively and skipping dotfiles, into
/// `files`.
fn collect(dir: &Path, files: &mut Vec<PathBuf>) {
    let entries =
        std::fs::read_dir(dir).unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()));

    for entry in entries {
        let path = entry
            .unwrap_or_else(|e| panic!("cannot read under {}: {e}", dir.display()))
            .path();
        let dotfile = path
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with('.'));
        if dotfile {
            continue;
        }
        if path.is_dir() {
            collect(&path, files);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            files.push(path);
        }
    }
}
