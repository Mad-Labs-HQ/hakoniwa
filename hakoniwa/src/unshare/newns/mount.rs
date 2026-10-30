//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
use nix::mount::MsFlags;

bitflags::bitflags! {
    /// Mount flags.
    ///
    /// [mount]: https://man7.org/linux/man-pages/man2/mount.2.html
    /// [mount.h]: https://github.com/torvalds/linux/blob/v6.13/include/uapi/linux/mount.h
    #[derive(Hash, Eq, PartialEq, Clone, Copy, Debug)]
    pub struct MountOptions: u32 {
        const RDONLY = 1;
        const NOSUID = 2;
        const NODEV  = 4;
        const NOEXEC = 8;
        const BIND   = 4096;
        const REC    = 16384;
    }
}

// Serialized as its bits, for a supervisor started from its own image; bits
// this build does not know are refused rather than dropped.
impl serde::Serialize for MountOptions {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serde::Serialize::serialize(&self.bits(), serializer)
    }
}

impl<'de> serde::Deserialize<'de> for MountOptions {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let bits = <u32 as serde::Deserialize>::deserialize(deserializer)?;
        Self::from_bits(bits)
            .ok_or_else(|| serde::de::Error::custom(format!("unknown mount option bits {bits:#x}")))
    }
}

impl MountOptions {
    pub(crate) fn to_ms_flags(self) -> MsFlags {
        let mut flags = MsFlags::empty();
        for option in self.iter() {
            match option {
                Self::RDONLY => flags.insert(MsFlags::MS_RDONLY),
                Self::NOSUID => flags.insert(MsFlags::MS_NOSUID),
                Self::NODEV => flags.insert(MsFlags::MS_NODEV),
                Self::NOEXEC => flags.insert(MsFlags::MS_NOEXEC),
                Self::BIND => flags.insert(MsFlags::MS_BIND),
                Self::REC => flags.insert(MsFlags::MS_REC),
                _ => {}
            }
        }
        flags
    }
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct Mount {
    pub(crate) source: String,
    pub(crate) target: String,
    pub(crate) fstype: String,
    pub(crate) options: MountOptions,
    pub(crate) data: Option<String>,
}

impl std::fmt::Display for Mount {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self.fstype.as_ref() {
            "proc" => return write!(f, "   proc: {}", self.target),
            "devfs" => return write!(f, "  devfs: {}", self.target),
            "tmpfs" => return write!(f, "  tmpfs: {}", self.target),
            "overlay" => return write!(f, "overlay: {}", self.target),
            _ => {}
        }

        if self.options & MountOptions::BIND == MountOptions::BIND {
            if self.options & MountOptions::RDONLY == MountOptions::RDONLY {
                return write!(f, "bind_ro: {} -> {}", self.source, self.target);
            } else {
                return write!(f, "bind_rw: {} -> {}", self.source, self.target);
            }
        }

        write!(f, "       : {}", self.target)
    }
}
