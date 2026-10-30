//! Runs failed-startup reaping checks in the fork or matched image mode.
//!
//! Image mode requires a helper built from the same sources and feature set.
//! Refused acquisition tests need the external syscall-refusal wrapper.

#[path = "support/setup_reaping.rs"]
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
