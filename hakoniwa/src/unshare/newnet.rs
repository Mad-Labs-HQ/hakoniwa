//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-06.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
//!
//! Sets up the configured network through the host namespace owner.
//!
//! Assumes the selected network adapter is present and its child is unreaped.

mod network;
mod pasta;

use crate::{Container, error::*};
use nix::unistd::Pid;

pub use network::Network;
pub use pasta::Pasta;

#[cfg(feature = "rustslirp")]
pub(crate) mod rustslirp;

pub(crate) enum SetupStatus {
    None,
    #[cfg(feature = "rustslirp")]
    RustSlirpTapFd(std::os::fd::RawFd),
}

pub(crate) fn mainp_setup(container: &Container, child: Pid) -> Result<SetupStatus> {
    let network = &container
        .network
        .clone()
        .expect("Container#network is some");
    let status = match network {
        Network::Pasta(pasta) => Pasta::mainp_setup(pasta, child)?,
        #[cfg(feature = "rustslirp")]
        Network::RustSlirp(rustslirp) => rustslirp::RustSlirp::mainp_setup(rustslirp, child)?,
    };

    log::debug!("================================");
    Ok(status)
}
