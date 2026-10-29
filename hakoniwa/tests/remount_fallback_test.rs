//! Checks read-only bind mounts when the unprivileged remount fallback is used.
//!
//! Requires native Linux namespaces and writable /dev/shm mounted nodev,nosuid.
//! A writable neighbor distinguishes the restriction from a failed mount setup.

use hakoniwa::{Container, Runctl};
use std::{fs, io};

/// Attempts both guest writes and checks the resulting host files and mount flags.
#[test]
fn fallback_preserves_requested_read_only_access() -> io::Result<()> {
    let directory = tempfile::tempdir_in("/dev/shm")?;
    let readonly = directory.path().join("readonly");
    let writable = directory.path().join("writable");
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

    let output = container
        .command("/bin/sh")
        .args([
            "-c",
            "touch /readonly/forbidden; \
             touch /writable/allowed || exit 42; \
             cat /proc/self/mountinfo",
        ])
        .output()
        .map_err(io::Error::other)?;

    assert!(
        output.status.success(),
        "guest setup or control failed: {:?}",
        output.status
    );
    assert!(writable.join("allowed").exists(), "writable control failed");
    assert!(
        !readonly.join("forbidden").exists(),
        "read-only bind mount accepted a guest write"
    );

    let mounts = String::from_utf8(output.stdout).map_err(io::Error::other)?;

    for (target, mode) in [("/readonly", "ro"), ("/writable", "rw")] {
        let options = mounts
            .lines()
            .find_map(|line| {
                let mut fields = line.split_whitespace();
                (fields.nth(4) == Some(target))
                    .then(|| fields.next())
                    .flatten()
            })
            .ok_or_else(|| io::Error::other("missing guest mount"))?;

        for required in [mode, "nodev", "nosuid"] {
            assert!(
                options.split(',').any(|flag| flag == required),
                "{target}: expected {required} in {options}"
            );
        }
    }

    Ok(())
}
