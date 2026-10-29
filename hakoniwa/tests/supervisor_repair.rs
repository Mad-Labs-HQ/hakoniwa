//! Checks that an image supervisor does not retain the host executable.
//!
//! Requires the separately built supervisor example at HAKONIWA_TEST_SUPERVISOR.
//! The external test driver builds it from the same dependency as this host.

use hakoniwa::{Container, Supervisor};
use std::{fs, io, path::PathBuf};

/// Observes the supervisor executable through procfs, then joins its command.
#[test]
#[ignore = "requires a separately built supervisor example"]
fn supervisor_executes_the_pinned_image() -> io::Result<()> {
    let image = std::env::var_os("HAKONIWA_TEST_SUPERVISOR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("supervisor path missing"))?;
    let mut child = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .command("/bin/cat")
        .supervisor(Supervisor::Image(image.clone()))
        .stdin(hakoniwa::Stdio::piped())
        .spawn()
        .map_err(io::Error::other)?;
    let result = fs::canonicalize(format!("/proc/{}/exe", child.id()));
    drop(child.stdin.take());
    let status = child.wait().map_err(io::Error::other)?;
    assert_eq!(result?, fs::canonicalize(image)?);
    assert!(status.success(), "{status:?}");
    Ok(())
}
