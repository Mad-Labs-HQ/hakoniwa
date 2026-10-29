//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
/// Represents a FS rule.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Rule {
    pub(crate) path: String,
    pub(crate) mode: super::Access,
}

impl std::fmt::Display for Rule {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} {}", self.mode, self.path)
    }
}
