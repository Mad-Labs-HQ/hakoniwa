//! Modification notice: Mad Labs, Inc added this file on 2026-10-29.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Checks the typed view against status constructors and the original wire shape.
//!
//! Assumes library reports use exit_code to distinguish exits from signals.
//! Synthetic signal cases test normalization, not native delivery of every signal.

use super::{ExitStatus, Termination};
use nix::sys::{signal::Signal, wait::WaitStatus};
use nix::unistd::Pid;

/// Constructs the original public record without adding a required field.
fn report(code: i32, exit_code: Option<i32>) -> ExitStatus {
    ExitStatus {
        code,
        reason: "legacy fixture".into(),
        exit_code,
        rusage: None,
        proc_pid_smaps_rollup: None,
        proc_pid_status: None,
    }
}

/// Requires each constructor's existing fields to retain its typed outcome.
#[test]
fn constructors_preserve_exit_and_signal_facts() {
    let container = crate::Container::new();
    let command = container.command("fixture");
    let pid = Pid::from_raw(1);

    for code in 0..=255 {
        let status = ExitStatus::from_wait_status(&WaitStatus::Exited(pid, code), &command);
        assert_eq!(status.termination(), Some(Termination::Exited(code)));
    }

    for signal in Signal::iterator() {
        let status =
            ExitStatus::from_wait_status(&WaitStatus::Signaled(pid, signal, false), &command);
        assert_eq!(
            status.termination(),
            Some(Termination::Signaled(signal as i32))
        );
    }
}

/// Prevents a container failure from becoming a fabricated exit or signal.
#[test]
fn container_failure_has_no_inner_termination() {
    assert_eq!(ExitStatus::new_failure("setup failed").termination(), None);
    assert_eq!(
        report(125, Some(125)).termination(),
        Some(Termination::Exited(125))
    );
    assert_eq!(
        report(137, Some(137)).termination(),
        Some(Termination::Exited(137))
    );
    assert_eq!(
        report(137, None).termination(),
        Some(Termination::Signaled(9))
    );
}

/// Rejects contradictory values without accepting a signal-shaped numeric exit.
#[test]
fn inconsistent_fields_have_no_typed_view() {
    for (code, exit_code) in [
        (-1, None),
        (0, None),
        (128, None),
        (256, None),
        (137, Some(0)),
        (137, Some(-1)),
        (256, Some(256)),
    ] {
        assert_eq!(report(code, exit_code).termination(), None);
    }
}

/// Treats reason as diagnostic text, independent of the structured fields.
#[test]
fn diagnostic_text_cannot_change_termination() {
    let numeric = ExitStatus {
        reason: "received signal SIGKILL".into(),
        ..report(137, Some(137))
    };
    let signaled = ExitStatus {
        reason: "exited normally".into(),
        ..report(137, None)
    };
    let failed = ExitStatus {
        reason: "process exited with code 137".into(),
        ..report(125, None)
    };

    assert_eq!(numeric.termination(), Some(Termination::Exited(137)));
    assert_eq!(signaled.termination(), Some(Termination::Signaled(9)));
    assert_eq!(failed.termination(), None);
}

/// Keeps a pre-accessor struct literal and its frozen Postcard bytes usable.
#[test]
fn original_public_record_and_wire_layout_survive() -> Result<(), postcard::Error> {
    let status = report(137, Some(137));
    // This fixture was encoded by the original six-field upstream record.
    let legacy = b"\x92\x02\x0elegacy fixture\x01\x92\x02\x00\x00\x00";
    assert_eq!(
        postcard::to_allocvec(&status)?,
        legacy,
        "typed accessor changed the legacy status wire shape"
    );
    let decoded = postcard::from_bytes::<ExitStatus>(legacy)?;
    assert_eq!((decoded.code, decoded.exit_code), (137, Some(137)));
    assert_eq!(decoded.termination(), Some(Termination::Exited(137)));
    Ok(())
}
