//! Modification notice: Mad Labs, Inc added this file on 2026-10-29.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Checks the native report fields and original serialized record layout.
//!
//! Assumes library constructors encode normal exits through exit_code. Signal
//! cases test normalization; they do not deliver every signal through the kernel.

use super::ExitStatus;
use nix::sys::{signal::Signal, wait::WaitStatus};
use nix::unistd::Pid;

/// Preserves the field pairs consumed by application-specific result adapters.
#[test]
fn constructors_preserve_exit_and_signal_fields() {
    let container = crate::Container::new();
    let command = container.command("fixture");
    let pid = Pid::from_raw(1);

    for code in 0..=255 {
        let status = ExitStatus::from_wait_status(&WaitStatus::Exited(pid, code), &command);
        assert_eq!((status.code, status.exit_code), (code, Some(code)));
    }

    for signal in Signal::iterator() {
        let status =
            ExitStatus::from_wait_status(&WaitStatus::Signaled(pid, signal, false), &command);
        assert_eq!((status.code, status.exit_code), (128 + signal as i32, None));
    }

    let failed = ExitStatus::new_failure("setup failed");
    assert_eq!((failed.code, failed.exit_code), (125, None));
}

/// Keeps an original public literal and its frozen Postcard bytes usable.
#[test]
fn original_public_record_and_wire_layout_survive() -> Result<(), postcard::Error> {
    let status = ExitStatus {
        code: 137,
        reason: "legacy fixture".into(),
        exit_code: Some(137),
        rusage: None,
        proc_pid_smaps_rollup: None,
        proc_pid_status: None,
    };
    // The frozen bytes came from the original upstream six-field record.
    let legacy = b"\x92\x02\x0elegacy fixture\x01\x92\x02\x00\x00\x00";
    assert_eq!(
        postcard::to_allocvec(&status)?,
        legacy,
        "native report changed the original wire shape"
    );
    let decoded = postcard::from_bytes::<ExitStatus>(legacy)?;
    assert_eq!((decoded.code, decoded.exit_code), (137, Some(137)));
    Ok(())
}
