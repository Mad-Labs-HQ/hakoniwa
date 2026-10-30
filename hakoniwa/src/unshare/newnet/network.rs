//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
/// Network mode.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub enum Network {
    Pasta(super::Pasta),
    #[cfg(feature = "rustslirp")]
    RustSlirp(super::rustslirp::RustSlirp),
}

impl From<super::Pasta> for Network {
    fn from(val: super::Pasta) -> Self {
        Self::Pasta(val)
    }
}

#[cfg(feature = "rustslirp")]
impl From<super::rustslirp::RustSlirp> for Network {
    fn from(val: super::rustslirp::RustSlirp) -> Self {
        Self::RustSlirp(val)
    }
}
