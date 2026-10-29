//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct WriteFile {
    pub(crate) target: String,
    pub(crate) contents: String,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct MakeDir {
    pub(crate) target: String,
    pub(crate) mode: u32,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct MakeSymlink {
    pub(crate) original: String,
    pub(crate) link: String,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) enum Operation {
    WriteFile(WriteFile),
    MakeDir(MakeDir),
    MakeSymlink(MakeSymlink),
}

impl From<WriteFile> for Operation {
    fn from(val: WriteFile) -> Self {
        Self::WriteFile(val)
    }
}

impl From<MakeDir> for Operation {
    fn from(val: MakeDir) -> Self {
        Self::MakeDir(val)
    }
}

impl From<MakeSymlink> for Operation {
    fn from(val: MakeSymlink) -> Self {
        Self::MakeSymlink(val)
    }
}

impl std::fmt::Display for Operation {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Self::WriteFile(file) => {
                write!(f, "  write: {}", file.target)
            }
            Self::MakeDir(dir) => {
                write!(f, "  mkdir: {}", dir.target)
            }
            Self::MakeSymlink(symlink) => {
                write!(f, "symlink: {} -> {}", symlink.link, symlink.original)
            }
        }
    }
}
