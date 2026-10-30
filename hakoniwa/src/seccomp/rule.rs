//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
use super::{Action, ArgCmp};

/// Represents a filter rule.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Rule {
    pub action: Action,
    pub sysname: String,
    pub(crate) argcmps: Vec<ArgCmp>,
}

impl std::fmt::Display for Rule {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let action = self.action;
        let sysname = &self.sysname;
        let argcmps = self
            .argcmps
            .iter()
            .map(|cmp| format!("{cmp}"))
            .collect::<Vec<_>>()
            .join(", ");

        if argcmps.is_empty() {
            write!(f, "{sysname}(..) -> {action:?}")
        } else {
            write!(f, "{sysname}({argcmps}, ..) -> {action:?}")
        }
    }
}
