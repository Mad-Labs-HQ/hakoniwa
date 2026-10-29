//! Exercises read-only fallback independently of Landlock.
//!
//! Requires /dev/shm mounted nodev,nosuid and native Linux namespaces. The
//! writable neighbor is a positive control for a functioning mount setup.

use hakoniwa::{Container, Runctl};
use std::{fs, io};

/// Checks mount flags and writes on read-only and writable fallback mounts.
#[test]
fn fallback_keeps_requested_read_only_and_a_writable_neighbor() -> io::Result<()> {
    let dir = tempfile::tempdir_in("/dev/shm")?;
    let readonly = dir.path().join("readonly");
    let writable = dir.path().join("writable");
    fs::create_dir(&readonly)?;
    fs::create_dir(&writable)?;
    let mut container = Container::new();
    container.rootfs("/").map_err(io::Error::other)?;
    container.runctl(Runctl::MountFallback);
    container.bindmount_ro(
        readonly
            .to_str()
            .ok_or_else(|| io::Error::other("path encoding"))?,
        "/readonly",
    );
    container.bindmount_rw(
        writable
            .to_str()
            .ok_or_else(|| io::Error::other("path encoding"))?,
        "/writable",
    );
    let output = container.command("/bin/sh").args(["-c",
        "if touch /readonly/forbidden; then exit 41; fi; touch /writable/allowed; cat /proc/self/mountinfo"])
        .output().map_err(io::Error::other)?;
    assert!(output.status.success(), "{:?}", output.status);
    assert!(!readonly.join("forbidden").exists());
    assert!(writable.join("allowed").exists());
    let mounts = String::from_utf8(output.stdout).map_err(io::Error::other)?;

    for (target, mode) in [("/readonly", "ro"), ("/writable", "rw")] {
        let options = mounts
            .lines()
            .find_map(|line| {
                let fields = line.split_whitespace().collect::<Vec<_>>();
                (fields.get(4) == Some(&target))
                    .then(|| fields.get(5).copied())
                    .flatten()
            })
            .ok_or_else(|| io::Error::other("missing guest mount"))?;
        assert!(
            options.split(',').any(|flag| flag == mode),
            "{target}: {options}"
        );
        assert!(options.split(',').any(|flag| flag == "nodev"));
        assert!(options.split(',').any(|flag| flag == "nosuid"));
    }

    Ok(())
}
