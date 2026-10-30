//! Compares native command configuration and stdio in Fork and Image modes.
//!
//! Requires namespaces and a matching HAKONIWA_TEST_SUPERVISOR. Each mode uses
//! fresh files because cloned input descriptors would share their file offset.

use hakoniwa::{Container, Supervisor};
use std::{fs, io, path::PathBuf};

/// Requires environment, arguments, cwd, writable mounts and all three streams.
fn check(supervisor: Supervisor) -> io::Result<()> {
    let directory = tempfile::tempdir()?;
    let input = directory.path().join("input");
    fs::write(&input, "payload\n")?;
    let mount = directory
        .path()
        .to_str()
        .ok_or_else(|| io::Error::other("path encoding"))?;
    let output = Container::new()
        .rootfs("/").map_err(io::Error::other)?
        .bindmount_rw(mount, "/work")
        .command("/bin/sh")
        .args(["-c", "printf '%s\\n' \"$TOKEN\" \"$PWD\"; cat; printf 'diagnostic\\n' >&2; printf written > result"])
        .env("TOKEN", "preserved")
        .current_dir("/work")
        .supervisor(supervisor)
        .stdin(fs::File::open(input)?)
        .output().map_err(io::Error::other)?;
    assert!(output.status.success(), "{:?}", output.status);
    assert_eq!(output.stdout, b"preserved\n/work\npayload\n");
    assert_eq!(output.stderr, b"diagnostic\n");
    assert_eq!(fs::read(directory.path().join("result"))?, b"written");
    Ok(())
}

/// Exercises the same settings through the public builder in both modes.
#[test]
#[ignore = "requires a separately built matching supervisor"]
fn configuration_and_stdio_match() -> io::Result<()> {
    let helper = std::env::var_os("HAKONIWA_TEST_SUPERVISOR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("matching supervisor missing"))?;
    check(Supervisor::Fork)?;
    check(Supervisor::Image(helper))
}
