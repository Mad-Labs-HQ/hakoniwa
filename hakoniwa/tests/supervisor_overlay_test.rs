//! Exercises 1.8.0 overlay mount data through a separately executed supervisor.
//!
//! Requires native Linux overlays, writable tmpfs at /dev/shm, and a matching
//! HAKONIWA_TEST_SUPERVISOR. Each mode uses fresh layers outside Docker's rootfs.

use hakoniwa::{Container, Supervisor};
use std::{fs, io, path::PathBuf};

/// Selects the matching helper explicitly so a fork-only test cannot pass.
fn image() -> io::Result<Supervisor> {
    std::env::var_os("HAKONIWA_TEST_SUPERVISOR")
        .map(PathBuf::from)
        .map(Supervisor::Image)
        .ok_or_else(|| io::Error::other("matching supervisor path missing"))
}

/// Requires the lower-layer list and read-only setting to survive execution.
fn check_read_only(supervisor: Supervisor) -> io::Result<()> {
    let directory = tempfile::tempdir_in("/dev/shm")?;
    let lower = directory.path().join("lower");
    let base = directory.path().join("base");
    fs::create_dir(&lower)?;
    fs::create_dir(&base)?;
    fs::write(lower.join("item"), "lower layer")?;
    fs::write(base.join("other"), "base layer")?;
    let lower = format!("{}:{}", lower.display(), base.display());
    let output = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .overlaymount_ro(&lower, "/layers")
        .command("/bin/sh")
        .args(["-c", "test \"$(cat /layers/item)\" = 'lower layer' && test \"$(cat /layers/other)\" = 'base layer' && ! printf changed > /layers/item"])
        .supervisor(supervisor)
        .output()
        .map_err(io::Error::other)?;

    assert!(
        output.status.success(),
        "{:?}: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

/// Requires upper and work directories to reach execution and accept writes.
fn check_writable(supervisor: Supervisor) -> io::Result<()> {
    let directory = tempfile::tempdir_in("/dev/shm")?;
    let lower = directory.path().join("lower");
    let upper = directory.path().join("upper");
    let work = directory.path().join("work");
    fs::create_dir(&lower)?;
    fs::create_dir(&upper)?;
    fs::create_dir(&work)?;
    fs::write(lower.join("item"), "unchanged lower")?;
    let output = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .overlaymount_rw(
            &lower.to_string_lossy(),
            &upper.to_string_lossy(),
            &work.to_string_lossy(),
            "/layers",
        )
        .command("/bin/sh")
        .args(["-c", "printf 'written in guest' > /layers/item"])
        .supervisor(supervisor)
        .output()
        .map_err(io::Error::other)?;

    assert!(
        output.status.success(),
        "{:?}: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(fs::read_to_string(upper.join("item"))?, "written in guest");
    assert_eq!(fs::read_to_string(lower.join("item"))?, "unchanged lower");
    Ok(())
}

/// Compares the native fork control with the separately executed supervisor.
#[test]
#[ignore = "requires a separately built supervisor image"]
fn image_preserves_read_only_overlay_data() -> io::Result<()> {
    check_read_only(Supervisor::Fork)?;
    check_read_only(image()?)
}

/// Requires guest writes to the upper layer in both supervisor modes.
#[test]
#[ignore = "requires a separately built supervisor image"]
fn image_preserves_writable_overlay_data() -> io::Result<()> {
    check_writable(Supervisor::Fork)?;
    check_writable(image()?)
}
