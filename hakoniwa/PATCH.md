# Hakoniwa 1.8.0 repair record

The upstream base is the published hakoniwa 1.8.0 crate, whose SHA-256 is
`6049661b562000cd560f3e481bc306b192ea6358c38b50955786d8e4c9b2a942`.
UPSTREAM-CHECKSUMS.json pins its original files. Reversing PATCH.diff recovers
those source files exactly. The source patch covers src; the separately added
build.rs fingerprints the image-supervisor protocol. The review records pin
both against the compiled staged port.

The upstream LGPL-3.0-only WITH LGPL-3.0-linking-exception license remains in
LICENSE. COPYING retains the incorporated GPLv3 text. Fork branding and the
surrounding project's Apache-2.0 license do not replace those terms.

## Repairs retained

A private startup handshake gates user code until the host pins the exclusively
owned inner PID with a pidfd. Failed startup either completes cleanup or retains
its authority. Cancellation targets the inner process even after it clears
PDEATHSIG. The acquired rootfs stays with Child until disposal.

A cached setup failure is distinct from a reaped supervisor result. Failed
startup retains its original error and any acquired workload descriptor.
`wait()` still reaps the supervisor; `try_wait()` reports no completion
while it is alive. This preserves supervisor identity acquisition after
`spawn()` and clears the pending-cleanup hint only after a kernel wait.

Report read or decode errors cannot undo kernel reaping. The first wait returns
its original typed error. Later waits report ChildExitStatusGone without another
kernel wait. The acquired workload pidfd and rootfs remain owned by Child, and
kill cannot signal a recycled numeric supervisor PID.

ExitStatus retains upstream's public fields and wire layout. Normal exits carry
exit_code; signal reports use 128 + signal without exit_code. Container failure
125 without exit_code carries no observed inner outcome. Consumers interpret
these fields at their own integration boundary. The fork adds no termination
enum, accessor or stored field.

Child::kill reports the inner signal result instead of a supervisor setup
failure. Hosts and image helpers must still be rebuilt together so their source
fingerprints match.

The remount fallback retains requested read-only access while incorporating
locked source-mount flags. Its native control also requires a writable neighbor.

A checked frame supports a supervisor started from its own executable image.
The host and helper must use matching source, manifest and features. Unknown
layout, malformed input and mismatched builds are refused. Closure commands
retain fork mode. Host applications assume exclusive reaping of these children.

The supervisor file-actions wrapper uses an exclusive mutable borrow when
libc appends descriptor actions. Its pointer comes from MaybeUninit::as_mut_ptr;
it is never written through a pointer derived from a shared Rust reference.
The source guard is an accidental-mismatch check, not authentication or proof
of identical compiler, target and dependency builds.

## Upstream 1.8.0 changes retained

The port keeps upstream's ptrace ESRCH continuation fix, mount-data and overlay
support, mount setup changes and dependency updates. Mount.data is serialized
with the rest of Container. Native tests compare fork and image overlays, then
challenge omission of that data and verify restored controls.

Tracing can observe an init's signal before its first stop. That early path has
no resource-usage measurement. Tests require the actual signal result in both
modes and resource usage where collection has occurred.

## Distribution boundary

This review candidate is mad-hakoniwa 1.8.0-mad.1; the Rust library is hakoniwa.
The source manifest keeps publish=false. Product checkouts use an exact sibling
path pin. The isolated registry rehearsal changes only a disposable copy to a
local HTTP registry and removes both fork checkout and vendor alternatives.
No package is published by these checks.

The 1.7.2 vendor tree is an archived baseline. It is not the linked library or
the current provenance reference. Upstream contributions are reviewed separately
from this integration branch.
