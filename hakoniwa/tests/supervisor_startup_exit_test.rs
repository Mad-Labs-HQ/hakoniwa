//! Requires partial-frame startup failure to retain the public cleanup contract.
//!
//! Assumes Linux pipes and a built startup-exit-fixture executable supplied by
//! HAKONIWA_TEST_EXIT_SUPERVISOR. The fixture reports actual pipe capacity so a
//! large configuration cannot silently turn this into a completed-write test.

use hakoniwa::{Container, Supervisor};
use nix::errno::Errno;
use nix::sys::wait::{WaitPidFlag, waitpid};
use nix::unistd::Pid;
use std::io::Write;
use std::{fs, io, path::PathBuf};

/// Forces a helper to exit before a full frame can be written, then checks wait.
#[test]
#[ignore = "requires the separately built startup-exit-fixture executable"]
fn partial_frame_write_failure_reaps_helper() -> io::Result<()> {
    let helper = std::env::var_os("HAKONIWA_TEST_EXIT_SUPERVISOR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("startup exit fixture missing"))?;
    let directory = tempfile::tempdir()?;
    let report = directory.path().join("partial-frame");
    let mount = directory
        .path()
        .to_str()
        .ok_or_else(|| io::Error::other("path encoding"))?;
    let padding = "x".repeat(8 * 1024 * 1024);
    let mut child = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .bindmount_rw(mount, "/work")
        .command("/bin/sh")
        .args(["-c", "printf executed > /work/ran"])
        .env("STARTUP_PADDING", &padding)
        .stdout(fs::File::create(&report)?)
        .supervisor(Supervisor::Image(helper))
        .spawn()
        .map_err(io::Error::other)?;
    let pid = Pid::from_raw(i32::try_from(child.id()).map_err(io::Error::other)?);
    let status = child.wait().map_err(io::Error::other)?;
    let observation = waitpid(pid, Some(WaitPidFlag::WNOHANG));
    let repeated = child.wait().map_err(io::Error::other)?;
    let values = fs::read_to_string(report)?
        .split_whitespace()
        .map(str::parse::<usize>)
        .collect::<Result<Vec<_>, _>>()
        .map_err(io::Error::other)?;
    let [observed_pid, capacity, body_length, consumed] = values.as_slice() else {
        return Err(io::Error::other("partial-frame witness incomplete"));
    };

    assert_eq!(
        *observed_pid,
        usize::try_from(child.id()).map_err(io::Error::other)?
    );
    assert_eq!(*consumed, 1);
    assert!(*body_length >= padding.len());
    assert!(
        *body_length > *capacity + *consumed,
        "fixture must close before the full frame can fit: {values:?}"
    );
    assert_eq!((status.code, status.exit_code), (125, None));
    assert!(!status.reason.is_empty());
    assert_eq!((repeated.code, repeated.exit_code), (125, None));
    assert_eq!(repeated.reason, status.reason);
    assert!(child.inner_pidfd().is_none());
    assert!(
        !directory.path().join("ran").exists(),
        "guest ran during failed startup"
    );
    assert!(
        matches!(observation, Err(Errno::ECHILD)),
        "partial-frame failure returned from wait without reaping: {observation:?}"
    );
    assert!(!child.startup_cleanup_pending());
    writeln!(
        io::stderr(),
        "partial frame: capacity={capacity}, body={body_length}, consumed={consumed}, status={status:?}"
    )?;
    Ok(())
}
