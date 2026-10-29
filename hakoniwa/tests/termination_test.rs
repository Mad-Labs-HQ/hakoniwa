//! Modification notice: Mad Labs, Inc added this file on 2026-10-29.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Checks typed outcomes against native process and setup reports.
//!
//! Requires Linux, /bin/sh and namespace support for the setup case. Empty
//! containers keep signal targets out of PID 1; they test reporting, not isolation.

use hakoniwa::{Container, ExitStatus, Stdio, Termination};

/// Observes an ordinary shell process so PID 1 cannot alter signal semantics.
fn shell_status(script: &str) -> hakoniwa::Result<ExitStatus> {
    Container::empty()
        .command("/bin/sh")
        .args(["-c", script])
        .wait_timeout(3)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .status()
}

/// Retains normal exit bytes even when they resemble a shell signal code.
#[test]
fn numeric_exits_are_not_signals() -> hakoniwa::Result<()> {
    for code in [0, 125, 129, 137, 255] {
        let status = shell_status(&format!("exit {code}"))?;
        assert_eq!((status.code, status.exit_code), (code, Some(code)));
        assert_eq!(status.termination(), Some(Termination::Exited(code)));
    }

    Ok(())
}

/// Distinguishes a real workload SIGKILL from normal exit 137.
#[test]
fn native_signal_retains_its_identity() -> hakoniwa::Result<()> {
    let status = shell_status("kill -KILL $$")?;
    assert_eq!((status.code, status.exit_code), (137, None));
    assert_eq!(status.termination(), Some(Termination::Signaled(9)));
    Ok(())
}

/// Rejects a mount during setup and requires absence of an inner outcome.
#[test]
fn setup_failure_has_no_inner_termination() -> hakoniwa::Result<()> {
    let status = Container::new()
        .rootfs("/")?
        .bindmount_ro("not-an-absolute-source", "/invalid")
        .command("/bin/true")
        .wait_timeout(3)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .status()?;
    assert_eq!(
        status.reason,
        "mount source path must be absolute: not-an-absolute-source"
    );
    assert_eq!((status.code, status.exit_code), (125, None));
    assert_eq!(status.termination(), None);
    Ok(())
}
