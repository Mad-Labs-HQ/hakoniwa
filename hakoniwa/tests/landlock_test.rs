//! Checks Landlock access values and the kernel capabilities used by its tests.
//!
//! The runtime check requires filesystem and TCP rules, available since ABI 4.
//! It creates a ruleset without restricting the test runner.

#[cfg(feature = "landlock")]
mod landlock {
    use ::landlock::{
        ABI, Access, AccessFs, AccessNet, CompatLevel, Compatible, Ruleset, RulesetAttr,
        RulesetError,
    };

    mod fs_access_test;

    /// Requires the suite's filesystem and TCP rights without compatibility fallback.
    /// Creating, then dropping, the strict ruleset leaves other test threads unrestricted.
    #[test]
    fn kernel_supports_filesystem_and_tcp_rules() -> Result<(), RulesetError> {
        Ruleset::default()
            .set_compatibility(CompatLevel::HardRequirement)
            .handle_access(AccessFs::from_all(ABI::V4))?
            .handle_access(AccessNet::from_all(ABI::V4))?
            .create()
            .map(drop)
    }
}
