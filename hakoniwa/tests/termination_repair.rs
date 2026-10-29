//! Distinguishes a numeric exit from a signal with the same shell code.
//!
//! Requires native Linux namespaces. Signal the acquired child from its host:
//! a namespace init process has special signal behavior and cannot serve as
//! an ordinary shell self-signal fixture.

use hakoniwa::{Container, Termination};
use std::io;

/// Compares numeric exit 137 with SIGKILL delivered through host ownership.
#[test]
fn exit_137_and_sigkill_keep_distinct_kernel_facts() -> io::Result<()> {
    let exited = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .command("/bin/sh")
        .args(["-c", "exit 137"])
        .status()
        .map_err(io::Error::other)?;
    assert_eq!(exited.code, 137);
    assert_eq!(exited.termination, Some(Termination::Exited(137)));

    let mut child = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .command("/bin/sleep")
        .arg("60")
        .spawn()
        .map_err(io::Error::other)?;
    child.kill().map_err(io::Error::other)?;
    let killed = child.wait().map_err(io::Error::other)?;
    assert_eq!(killed.code, 137);
    assert_eq!(killed.termination, Some(Termination::Signaled(9)));
    Ok(())
}
