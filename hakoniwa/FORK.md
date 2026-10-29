# Maintenance fork candidate

Package: `mad-hakoniwa` 1.8.0-mad.1. Rust library: `hakoniwa`.
Status: local review candidate. The public upstream fork exists at
https://github.com/Mad-Labs-HQ/hakoniwa. Our repairs remain local; no package has
been published.

This fork starts from published hakoniwa 1.8.0 and carries the ownership,
termination, read-only fallback and separate-supervisor repairs used by Mad
Sandbox. Its library source and build script match the staged native port.
PATCH.md, PATCH.diff and UPSTREAM-CHECKSUMS.json record provenance.

The original LGPL-3.0-only WITH LGPL-3.0-linking-exception license applies.
LICENSE and COPYING are included. The fork is not covered by Mad Sandbox's
Apache-2.0 license. This record does not replace a release rights review.

Use the explicit package alias after a reviewed release:

```toml
[target.'cfg(target_os = "linux")'.dependencies]
hakoniwa = { package = "mad-hakoniwa", version = "=1.8.0-mad.1", features = ["landlock"] }
```

The alias keeps Rust call sites unchanged. The clean-install rehearsal uses
this declaration with an explicit loopback registry. It never uses a path or
Git override for this dependency.

The fork follows pinned upstream v1.8.0. The 1.7.2 candidate, patch series and
registry receipts remain as the comparison baseline. The inherited CLI is
excluded from the workspace; this candidate contains the library.

## Returning upstream

Switch back only when a published upstream version supplies all required
behavior and passes the cancellation, startup failure, rootfs lifetime,
termination, remount and separate-image regression checks. Do not switch on
PR acceptance alone. Mark the fork superseded, retain published versions and
leave migration instructions.

The source manifest has `publish = false` as a review guard. Remove it only
after approval, then repackage and requalify the final artifact.

## Before any public release

- Review package name, version, ownership and provenance
- Set the reviewed fork commit and repository metadata
- Review the candidate crate file list and license records
- Repeat registry and native tests for the exact final artifact
- Review upstream submissions and patch order separately
- Publish only after explicit authorization

The inherited upstream release workflow is removed from this local candidate.
No tools in tools/ upload a package or submit a patch.
