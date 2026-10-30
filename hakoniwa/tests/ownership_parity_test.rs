//! Checks cancellation and rootfs lifetime in the fork or matched image mode.
//!
//! Image mode requires a helper built from the same sources and feature set.
//! The shared body uses an independent pidfd observer for cleanup.

#[path = "support/ownership_parity.rs"]
mod shared;

/// Selects a matched supervisor image when the native test driver supplies it.
fn configure_command(command: &mut hakoniwa::Command) -> std::io::Result<()> {
    let supervisor = match std::env::var_os("HAKONIWA_TEST_SUPERVISOR") {
        Some(image) => hakoniwa::Supervisor::Image(image.into()),
        None => hakoniwa::Supervisor::Fork,
    };
    command.supervisor(supervisor);
    Ok(())
}
