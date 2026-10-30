//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
bitflags::bitflags! {
    /// NET access flags.
    #[derive(Hash, Eq, PartialEq, Clone, Copy, Debug)]
    pub struct Access: u64 {
        const    TCP_BIND = 1;
        const TCP_CONNECT = 1 << 1;
    }
}

// Serialized as its bits, for a supervisor started from its own image; bits
// this build does not know are refused rather than dropped.
impl serde::Serialize for Access {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serde::Serialize::serialize(&self.bits(), serializer)
    }
}

impl<'de> serde::Deserialize<'de> for Access {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let bits = <u64 as serde::Deserialize>::deserialize(deserializer)?;
        Self::from_bits(bits).ok_or_else(|| {
            serde::de::Error::custom(format!("unknown landlock net access bits {bits:#x}"))
        })
    }
}

impl std::fmt::Display for Access {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut str = vec![];
        for e in [Self::TCP_BIND, Self::TCP_CONNECT] {
            str.push(match *self & e {
                Self::TCP_BIND => "tcp.bind",
                Self::TCP_CONNECT => "tcp.connect",
                _ => continue,
            });
        }
        write!(f, "{}", str.join(" | "))
    }
}
