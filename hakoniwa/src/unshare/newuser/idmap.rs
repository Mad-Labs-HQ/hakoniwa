//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct IdMap {
    pub(crate) container_id: u32,
    pub(crate) host_id: u32,
    pub(crate) size: u32,
}

impl IdMap {
    pub(crate) fn to_line(&self) -> String {
        format!("{} {} {}\n", self.container_id, self.host_id, self.size)
    }
}

impl std::fmt::Display for IdMap {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "container_id: {}, host_id: {}, count: {}",
            self.container_id, self.host_id, self.size
        )
    }
}
