//! Modification notice: Mad Labs, Inc added this file; changes recorded through
//! 2026-10-28.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Starts a command's supervisor from its own program image instead of a fork
//! of the calling process, and runs as that supervisor.
//!
//! A forked supervisor lives for the whole run as a copy-on-write image of the
//! caller, and every page the caller writes afterwards is duplicated into it,
//! so a large busy host pays its own size again per live run. A supervisor
//! started from [`Supervisor::Image`] holds only that image. The host sends the
//! command over the startup control pipe as one [`Frame`]; the supervisor then
//! runs the same `runc::exec` a forked one runs, so the startup gate, the
//! status pipe and the host's pinning of the inner process are unchanged.
//!
//! Assumes the image's `main` calls [`supervise`] first, and that host and
//! image were built from the same hakoniwa: every frame carries this build's
//! [`SUPERVISOR_FINGERPRINT`] (its sources and features, from `build.rs`), and
//! a supervisor from another build refuses the run with a reason, through the
//! status pipe as any setup failure, rather than read a layout it may not
//! share. A body it does not read to its last byte is refused too.
//!
//! Gotcha: the supervisor finds its control reader at descriptor 3 and its
//! status writer at 4. Every source descriptor is first moved above
//! [`SPARE_FD`], so that placing one never overwrites another still to place.

use std::ffi::CString;
use std::io::{PipeReader, PipeWriter, Read};
use std::mem::MaybeUninit;
use std::os::fd::{FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::ptr;

use nix::fcntl::{FcntlArg, fcntl};
use nix::unistd::Pid;

use crate::{Command, error::*};

/// How [`Command::spawn`](crate::Command::spawn) starts a command's supervisor.
#[derive(Clone, Debug)]
pub enum Supervisor {
    /// Fork the calling process, as upstream hakoniwa does. The supervisor
    /// keeps a copy-on-write image of the caller for the whole run.
    Fork,
    /// Start this program, whose `main` calls [`supervise`] first. The
    /// supervisor holds only its own image.
    Image(PathBuf),
}

/// The frame header's layout.
const FRAME_VERSION: u16 = 2;

/// This build's fingerprint, which every frame carries: a hash of hakoniwa's
/// sources and enabled features, so only a supervisor of the same build reads
/// a host's frames.
pub const SUPERVISOR_FINGERPRINT: &str = env!("HAKONIWA_FRAME_FINGERPRINT");

/// What every reason a supervisor refuses a run for begins with. Hosts of
/// other builds match on it, so its text never changes.
pub const SUPERVISOR_REFUSAL: &str = "the sandbox supervisor refused the run";

/// The header's length: magic, version, fingerprint, body length.
const HEADER_LEN: usize = 4 + 2 + SUPERVISOR_FINGERPRINT.len() + 4;

/// What opens every frame, so another program's bytes are refused by name.
const FRAME_MAGIC: [u8; 4] = *b"HKSV";

/// The most a frame body may claim, against a corrupt length.
const FRAME_LIMIT: u32 = 16 << 20;

/// Where a supervisor finds its startup control reader.
const CONTROL_FD: RawFd = 3;

/// Where a supervisor finds its status writer.
const STATUS_FD: RawFd = 4;

/// The lowest descriptor a source is moved to before placement.
const SPARE_FD: RawFd = 10;

/// What a supervisor needs of a command: everything `runc::exec` reads of it,
/// sent as one frame on the startup control pipe.
#[derive(serde::Serialize, serde::Deserialize)]
pub(crate) struct Frame {
    pub(crate) container: crate::Container,
    pub(crate) program: String,
    pub(crate) args: Vec<String>,
    pub(crate) envs: std::collections::HashMap<String, String>,
    pub(crate) dir: Option<PathBuf>,
    pub(crate) wait_timeout: Option<u64>,
    pub(crate) runtime_mount_oldproc: String,
    pub(crate) runtime_rootdir_abspath: PathBuf,
}

impl Frame {
    /// The frame as written: its magic, version, this build's fingerprint and
    /// body length, then the postcard body.
    pub(crate) fn encode(&self) -> Result<Vec<u8>> {
        let body = postcard::to_allocvec(self).map_err(|e| io_error(&e.to_string()))?;
        let len = u32::try_from(body.len())
            .ok()
            .filter(|len| *len <= FRAME_LIMIT)
            .ok_or_else(|| io_error("the supervisor frame is too large"))?;

        Ok([
            &FRAME_MAGIC[..],
            &FRAME_VERSION.to_le_bytes(),
            SUPERVISOR_FINGERPRINT.as_bytes(),
            &len.to_le_bytes(),
            &body,
        ]
        .concat())
    }

    /// Reads one frame from `control`, and no byte past it: the startup
    /// protocol continues on the same pipe. Another program's bytes, another
    /// header layout, another build's frame, a pipe that ends early, or a body
    /// that does not read to its last byte are refused with why.
    fn read(control: &mut PipeReader) -> std::result::Result<Self, String> {
        let mut head = [0; HEADER_LEN];
        control
            .read_exact(&mut head)
            .map_err(|e| format!("no supervisor frame from the host: {e}"))?;
        let (magic, rest) = head.split_at(4);
        let (version, rest) = rest.split_at(2);
        let (fingerprint, len) = rest.split_at(SUPERVISOR_FINGERPRINT.len());

        if magic != FRAME_MAGIC {
            return Err("the host did not send a supervisor frame".to_owned());
        }

        let version = u16::from_le_bytes([version[0], version[1]]);
        if version != FRAME_VERSION {
            return Err(format!(
                "the host wrote frame header version {version}, and this supervisor reads \
                 version {FRAME_VERSION}: the host and its supervisor image come from different \
                 builds; rebuild them together and restart the host"
            ));
        }

        if fingerprint != SUPERVISOR_FINGERPRINT.as_bytes() {
            return Err(format!(
                "the host is build {}, and this supervisor is build {SUPERVISOR_FINGERPRINT}: the \
                 host and its supervisor image come from different builds; rebuild them \
                 together and restart the host",
                String::from_utf8_lossy(fingerprint)
            ));
        }

        let len = u32::from_le_bytes([len[0], len[1], len[2], len[3]]);
        if len > FRAME_LIMIT {
            return Err(format!("the supervisor frame claims {len} bytes"));
        }

        let mut body = vec![0; len as usize];
        control
            .read_exact(&mut body)
            .map_err(|e| format!("the supervisor frame ended early: {e}"))?;
        let (frame, unread) = postcard::take_from_bytes::<Self>(&body)
            .map_err(|e| format!("the supervisor frame did not read: {e}"))?;
        if !unread.is_empty() {
            return Err(format!(
                "the supervisor frame carries {} bytes this supervisor does not read",
                unread.len()
            ));
        }

        Ok(frame)
    }
}

/// Starts `image` as a command's supervisor, with `stdio` (where given) at
/// descriptors 0 to 2, `control` at 3 and `status` at 4, an empty environment,
/// and no other argument; returns its pid.
///
/// Each source is first duplicated above [`SPARE_FD`] with close-on-exec, so
/// placements never overwrite one another and the duplicates vanish at exec.
/// A standard stream not given is inherited, as a forked supervisor inherits
/// it. `posix_spawn` copies no page of the caller and reports a failed exec.
pub(crate) fn spawn(
    image: &Path,
    stdio: [Option<RawFd>; 3],
    control: RawFd,
    status: RawFd,
) -> Result<Pid> {
    let placements = stdio
        .into_iter()
        .zip(0..)
        .filter_map(|(source, target)| source.map(|source| (source, target)))
        .chain([(control, CONTROL_FD), (status, STATUS_FD)])
        .map(|(source, target)| spare(source).map(|spare| (spare, target)))
        .collect::<Result<Vec<_>>>()?;
    let program = CString::new(image.as_os_str().as_bytes())
        .map_err(|_| io_error("the supervisor image path holds a NUL byte"))?;
    let argv = [program.as_ptr().cast_mut(), ptr::null_mut()];
    let envp = [ptr::null_mut::<libc::c_char>()];
    let actions = FileActions::new()?;

    for (spare, target) in &placements {
        actions.dup2(spare, *target)?;
    }

    let mut pid: libc::pid_t = 0;
    // SAFETY: `program`, `argv` and `envp` are NUL-terminated and outlive the
    // call; `actions` is initialized and outlives it; a null attribute pointer
    // asks for the defaults.
    let spawned = unsafe {
        libc::posix_spawn(
            &mut pid,
            program.as_ptr(),
            actions.as_ptr(),
            ptr::null(),
            argv.as_ptr(),
            envp.as_ptr(),
        )
    };

    match spawned {
        0 => Ok(Pid::from_raw(pid)),
        errno => Err(ProcessErrorKind::StdIoError(
            std::io::Error::from_raw_os_error(errno),
        ))?,
    }
}

/// A duplicate of `fd` above [`SPARE_FD`], closed at exec.
fn spare(fd: RawFd) -> Result<OwnedFd> {
    let spare =
        fcntl(fd, FcntlArg::F_DUPFD_CLOEXEC(SPARE_FD)).map_err(ProcessErrorKind::NixError)?;
    // SAFETY: fcntl just returned this descriptor, and nothing else owns it.
    Ok(unsafe { OwnedFd::from_raw_fd(spare) })
}

/// A `posix_spawn` file-actions list, destroyed on drop.
struct FileActions(Box<MaybeUninit<libc::posix_spawn_file_actions_t>>);

impl FileActions {
    /// An empty list.
    fn new() -> Result<Self> {
        let mut actions = Box::new(MaybeUninit::uninit());
        // SAFETY: init writes the list into the storage it is given.
        match unsafe { libc::posix_spawn_file_actions_init(actions.as_mut_ptr()) } {
            0 => Ok(Self(actions)),
            errno => Err(ProcessErrorKind::StdIoError(
                std::io::Error::from_raw_os_error(errno),
            ))?,
        }
    }

    /// Adds: duplicate `source` onto `target` in the child.
    fn dup2(&self, source: &OwnedFd, target: RawFd) -> Result<()> {
        use std::os::fd::AsRawFd;
        // SAFETY: the list was initialized in `new` and lives in its box, which
        // never moves; libc only appends to it.
        match unsafe {
            libc::posix_spawn_file_actions_adddup2(
                self.0.as_ptr().cast_mut(),
                source.as_raw_fd(),
                target,
            )
        } {
            0 => Ok(()),
            errno => Err(ProcessErrorKind::StdIoError(
                std::io::Error::from_raw_os_error(errno),
            ))?,
        }
    }

    fn as_ptr(&self) -> *const libc::posix_spawn_file_actions_t {
        self.0.as_ptr()
    }
}

impl Drop for FileActions {
    fn drop(&mut self) {
        // SAFETY: the list was initialized in `new` and is destroyed once.
        unsafe { libc::posix_spawn_file_actions_destroy(self.0.as_mut_ptr()) };
    }
}

/// Runs this process as the supervisor of the command its host sends: what a
/// [`Supervisor::Image`] program's `main` calls first. Never returns.
///
/// Its host started it with the startup control reader at descriptor 3 and the
/// status writer at 4. A frame that does not read is reported as the run's
/// failure on the status writer. Started any other way (by hand, say), it says
/// so on stderr and exits with code 2.
pub fn supervise() -> ! {
    let (Some(control), Some(status)) = (inherited(CONTROL_FD), inherited(STATUS_FD)) else {
        eprintln!("hakoniwa: a supervisor runs only when a sandbox host starts it");
        std::process::exit(2)
    };
    let mut control = PipeReader::from(control);
    let status = PipeWriter::from(status);

    match Frame::read(&mut control) {
        Ok(frame) => Command::supervise(frame, control, status),
        Err(reason) => crate::runc::fail(status, &format!("{SUPERVISOR_REFUSAL}: {reason}")),
    }
}

/// The descriptor `fd`, owned, when this process holds it open.
fn inherited(fd: RawFd) -> Option<OwnedFd> {
    fcntl(fd, FcntlArg::F_GETFD).ok().map(|_| {
        // SAFETY: the descriptor is open, and only this function claims the
        // two the host placed for its supervisor.
        unsafe { OwnedFd::from_raw_fd(fd) }
    })
}

fn io_error(reason: &str) -> Error {
    Error::ProcessError(ProcessErrorKind::StdIoError(std::io::Error::other(
        reason.to_owned(),
    )))
}
