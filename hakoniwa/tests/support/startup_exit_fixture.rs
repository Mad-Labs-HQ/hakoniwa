//! Ends a supervisor startup after reading a frame header and one body byte.
//!
//! Assumes Command placed its control pipe at descriptor 3 and a witness file
//! at stdout. This test fixture never enters sandbox setup or executes a guest.
//! The frame must exceed the pipe capacity plus the consumed prefix.

use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::FromRawFd;
use std::process::ExitCode;

/// Records the real pipe capacity and partial read before closing the reader.
fn main() -> io::Result<ExitCode> {
    // SAFETY: fcntl inspects descriptor 3 without changing or claiming it.
    let capacity = unsafe { libc::fcntl(3, libc::F_GETPIPE_SZ) };
    let capacity = usize::try_from(capacity).map_err(|_| io::Error::last_os_error())?;
    // SAFETY: Command supplies this open pipe; this fixture alone takes ownership.
    let mut control = unsafe { File::from_raw_fd(3) };
    let mut header = [0; 4 + 2 + hakoniwa::SUPERVISOR_FINGERPRINT.len() + 4];
    control.read_exact(&mut header)?;
    let encoded_length = header[header.len() - 4..]
        .try_into()
        .map_err(io::Error::other)?;
    let body_length = u32::from_le_bytes(encoded_length);
    let mut prefix = [0; 1];
    control.read_exact(&mut prefix)?;

    let mut witness = io::stdout().lock();
    writeln!(
        witness,
        "{} {capacity} {body_length} {}",
        std::process::id(),
        prefix.len()
    )?;
    witness.flush()?;
    Ok(ExitCode::from(17))
}
