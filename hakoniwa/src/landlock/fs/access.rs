//! Modification notice: Mad Labs, Inc changed this file; changes recorded through
//! 2026-10-27.
//! Licensed under LGPL-3.0-only WITH LGPL-3.0-linking-exception.
bitflags::bitflags! {
    /// FS access flags.
    #[derive(Hash, Eq, PartialEq, Clone, Copy, Debug)]
    pub struct Access: u64 {
        const R = 1;
        const W = 1 << 1;
        const X = 1 << 2;
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
            serde::de::Error::custom(format!("unknown landlock fs access bits {bits:#x}"))
        })
    }
}

impl std::fmt::Display for Access {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut str = "".to_string();
        for e in [Self::R, Self::W, Self::X] {
            str.push(match *self & e {
                Self::R => 'r',
                Self::W => 'w',
                Self::X => 'x',
                _ => '-',
            });
        }
        write!(f, "{str}")
    }
}

impl std::str::FromStr for Access {
    type Err = crate::Error;

    fn from_str(str: &str) -> Result<Self, Self::Err> {
        let mut access = Self::empty();
        for e in str.chars().collect::<Vec<char>>() {
            match e.to_lowercase().to_string().as_ref() {
                "r" => access |= Self::R,
                "w" => access |= Self::W,
                "x" => access |= Self::X,
                "-" => (),
                chr => {
                    let err = format!("landlock: unknown access {chr:?}");
                    Err(Self::Err::UnError(err))?
                }
            };
        }
        Ok(access)
    }
}
