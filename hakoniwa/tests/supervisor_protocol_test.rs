//! Checks helper refusal and startup errors through the public process API.
//!
//! Explicit image tests require HAKONIWA_TEST_SUPERVISOR from the same build.
//! Descriptor placement runs in a child and never changes the test runner.

use hakoniwa::{Container, ExitStatus, Supervisor};
use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};

/// Requires a matching helper instead of silently exercising the fork default.
fn helper() -> io::Result<PathBuf> {
    std::env::var_os("HAKONIWA_TEST_SUPERVISOR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("matching supervisor path missing"))
}

/// Places the input sources above reserved slots before the child is spawned.
fn duplicate(fd: RawFd) -> io::Result<OwnedFd> {
    // SAFETY: fcntl only reads this open descriptor and returns a new one.
    let copy = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 100) };

    if copy < 0 {
        return Err(io::Error::last_os_error());
    }

    // SAFETY: successful fcntl returned a fresh descriptor owned only here.
    Ok(unsafe { OwnedFd::from_raw_fd(copy) })
}

/// Runs one malformed frame and retains the helper's structured failure report.
fn refused(frame: &[u8]) -> io::Result<ExitStatus> {
    let (control_reader, mut control_writer) = std::io::pipe()?;
    let (mut status_reader, status_writer) = std::io::pipe()?;
    let control_copy = duplicate(control_reader.as_raw_fd())?;
    let status_copy = duplicate(status_writer.as_raw_fd())?;
    let control = control_copy.as_raw_fd();
    let status = status_copy.as_raw_fd();
    let mut command = Command::new(helper()?);
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // SAFETY: only async-signal-safe dup2 runs before exec. Both sources stay
    // owned in the parent through spawn and lie above the reserved target slots.
    unsafe {
        command.pre_exec(move || {
            if libc::dup2(control, 3) < 0 || libc::dup2(status, 4) < 0 {
                return Err(io::Error::last_os_error());
            }

            Ok(())
        });
    }

    let mut child = command.spawn()?;
    drop(control_copy);
    drop(status_copy);
    drop(control_reader);
    drop(status_writer);
    // Refusal may precede a complete write; EOF must still reach the helper.
    let _ = control_writer.write_all(frame);
    drop(control_writer);
    let mut report = Vec::new();
    let read = status_reader.read_to_end(&mut report);
    let waited = child.wait();
    read?;
    assert_eq!(waited?.code(), Some(125));
    assert_eq!(report.first(), Some(&0));
    postcard::from_bytes(&report[1..]).map_err(io::Error::other)
}

/// Uses the current header while keeping invalid payloads explicit in each case.
fn header(version: u16, fingerprint: &[u8], length: u32) -> Vec<u8> {
    [
        &b"HKSV"[..],
        &version.to_le_bytes(),
        fingerprint,
        &length.to_le_bytes(),
    ]
    .concat()
}

/// Rejects wrong, truncated and oversized startup data without executing a guest.
#[test]
#[ignore = "requires a separately built matching supervisor"]
fn malformed_frames_report_refusal() -> io::Result<()> {
    let ours = hakoniwa::SUPERVISOR_FINGERPRINT.as_bytes();
    let mut other = ours.to_vec();
    other[0] ^= 1;
    let cases = [
        (vec![b'x'; 26], "did not send a supervisor frame"),
        (header(999, ours, 0), "frame header version 999"),
        (header(2, &other, 0), "come from different builds"),
        (
            [header(2, ours, 64), b"short".to_vec()].concat(),
            "ended early",
        ),
        ([header(2, ours, 3), vec![0xff; 3]].concat(), "did not read"),
        (header(2, ours, (16 << 20) + 1), "claims"),
        (b"HK".to_vec(), "no supervisor frame"),
    ];

    for (frame, reason) in cases {
        let report = refused(&frame)?;
        assert!(report.reason.starts_with(hakoniwa::SUPERVISOR_REFUSAL));
        assert!(report.reason.contains(reason), "{report:?}");
        assert_eq!(report.exit_code, None);
    }

    Ok(())
}

/// Keeps the declared frame body from hiding unread configuration bytes.
#[test]
#[ignore = "requires a separately built matching supervisor"]
fn trailing_body_bytes_are_refused() -> io::Result<()> {
    // Postcard structs and tuples encode these fields in source order. This
    // fixture mirrors Frame solely to reach its unread-body rejection branch.
    let mut body = postcard::to_allocvec(&(
        Container::empty(),
        "/bin/true",
        Vec::<String>::new(),
        HashMap::<String, String>::new(),
        Option::<PathBuf>::None,
        Option::<u64>::None,
        String::new(),
        PathBuf::new(),
    ))
    .map_err(io::Error::other)?;
    body.push(0);
    let length = u32::try_from(body.len()).map_err(io::Error::other)?;
    let frame = [
        header(2, hakoniwa::SUPERVISOR_FINGERPRINT.as_bytes(), length),
        body,
    ]
    .concat();
    let report = refused(&frame)?;
    assert!(
        report
            .reason
            .contains("bytes this supervisor does not read"),
        "{report:?}"
    );
    Ok(())
}

/// Reports launch failure before producing a Child when the helper is absent.
#[test]
fn missing_helper_is_a_spawn_error() -> io::Result<()> {
    let directory = tempfile::tempdir()?;
    let result = Container::new()
        .command("/bin/true")
        .supervisor(Supervisor::Image(directory.path().join("missing")))
        .spawn();
    assert!(matches!(result, Err(hakoniwa::Error::ProcessError(_))));
    Ok(())
}

/// Rejects non-transferable closures before attempting to launch the image.
#[test]
fn image_rejects_closures_before_launch() -> io::Result<()> {
    // SAFETY: this constant closure does not allocate, lock or use host state.
    let mut command = unsafe { Container::empty().command_from_closure(|| 0) };
    command.supervisor(Supervisor::Image(PathBuf::from("/missing-helper")));
    let result = command.spawn();
    let Err(error) = result else {
        return Err(io::Error::other(
            "closure unexpectedly launched under an image",
        ));
    };
    assert!(error.to_string().contains("a closure command cannot run"));
    Ok(())
}
