//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
use super::{Cpu, Memory, Pids, error::*};

/// Control groups resources builder.
#[derive(Clone, Default, Debug, serde::Serialize, serde::Deserialize)]
pub struct Resources {
    cpu: Option<Cpu>,
    memory: Option<Memory>,
    pids: Option<Pids>,
}

impl Resources {
    /// Sets the cgroup cpu.
    pub fn cpu(&mut self, cpu: Cpu) -> &mut Self {
        self.cpu = Some(cpu);
        self
    }

    /// Sets the cgroup memory.
    pub fn memory(&mut self, memory: Memory) -> &mut Self {
        self.memory = Some(memory);
        self
    }

    /// Sets the cgroup pids.
    pub fn pids(&mut self, pids: Pids) -> &mut Self {
        self.pids = Some(pids);
        self
    }

    /// Build.
    pub(crate) fn build(&self) -> Result<oci_spec::runtime::LinuxResources> {
        let mut builder = oci_spec::runtime::LinuxResourcesBuilder::default();
        if let Some(res) = &self.cpu {
            builder = builder.cpu(res.build()?);
        }
        if let Some(res) = &self.memory {
            builder = builder.memory(res.build()?);
        }
        if let Some(res) = &self.pids {
            builder = builder.pids(res.build()?);
        }
        Ok(builder.build()?)
    }
}
