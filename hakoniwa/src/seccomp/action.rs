//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
/// Represents an action to be taken on a filter rule.
#[derive(Hash, Eq, PartialEq, Clone, Copy, Debug, serde::Serialize, serde::Deserialize)]
pub enum Action {
    Allow,
    Errno(i32),
    KillProcess,
    KillThread,
    Log,
    Notify,
    Trace(u16),
    Trap,
}
