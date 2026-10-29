//! Checks the repaired library API after resolution from a registry archive.
//!
//! Requires native Linux namespaces. No SDK or Mad Sandbox source is imported.

use hakoniwa::{Container, Termination};
use std::io;

/// Runs a short guest and requires an observed successful process exit.
fn main() -> io::Result<()> {
    let status = Container::new()
        .rootfs("/")
        .map_err(io::Error::other)?
        .command("/bin/true")
        .status()
        .map_err(io::Error::other)?;
    match status.termination {
        Some(Termination::Exited(0)) => Ok(()),
        other => Err(io::Error::other(format!(
            "unexpected termination: {other:?}"
        ))),
    }
}
