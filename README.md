# Hakoniwa

Process isolation for Linux using namespaces, resource limits, cgroups, landlock and seccomp.
It works by creating a new, completely empty, mount namespace where the root is
on a tmpdir, and will be automatically cleaned up when the last process exits.

It uses the following techniques:

- **Linux namespaces:** Create an isolated environment for the process.
- **MNT namespace + pivot_root:** Create a new root file system for the process.
- **NETWORK namespace + pasta**: Create a new user-mode networking stack for the process.
- **setrlimit:** Limit the amount of resources that can be used by the process.
- **cgroups + systemd:** Limit process resources using cgroup v2.
- **landlock:** Restrict ambient rights (e.g. global filesystem access) for the process.
- **seccomp:** Restrict the system calls that the process can make.

It can help you with:

- Compile source code in a restricted sandbox, e.g. [makepkg](https://github.com/souk4711/hakoniwa/tree/main/hakoniwa-cli/docs/app-makepkg)
- Run browsers, or proprietary softwares in an isolated environment, e.g. [Firefox](https://github.com/souk4711/hakoniwa/tree/main/hakoniwa-cli/docs/app-firefox)
- Chroot into rootfs, install GUI apps, and launch them, e.g. [containerized Firefox](https://github.com/souk4711/hakoniwa/tree/main/hakoniwa-cli/docs/container-firefox)

It also provides a set of profiles for the desktop application, read [Hakoniwa.d](https://github.com/souk4711/hakoniwa.d) to learn more.

> [!WARNING]
> Running untrusted code is never safe, sandboxing cannot change this.

## Installation

See [INSTALL.md](https://github.com/souk4711/hakoniwa/blob/main/INSTALL.md) for installation instructions.

## Usage

### CLI

```console
$ hakoniwa run -- sh
sh-5.2$ pwd
/
sh-5.2$ ls
bin  etc  lib  lib64  proc  sbin  usr
sh-5.2$ ls /proc
1           bus        crypto         execdomains  ioports    kmsg         meminfo  net           self      sysrq-trigger  version
3           cgroups    devices        fb           irq        kpagecgroup  misc     pagetypeinfo  slabinfo  sysvipc        vmallocinfo
acpi        cmdline    diskstats      filesystems  kallsyms   kpagecount   modules  partitions    softirqs  thread-self    vmstat
asound      config.gz  dma            fs           kcore      kpageflags   mounts   pressure      stat      timer_list     zoneinfo
bootconfig  consoles   driver         interrupts   key-users  loadavg      mtd      schedstat     swaps     tty
buddyinfo   cpuinfo    dynamic_debug  iomem        keys       locks        mtrr     scsi          sys       uptime
sh-5.2$ ps aux
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
johndoe        1  0.0  0.0   4708  4020 ?        S    21:22   0:00 /usr/bin/sh
johndoe        4  0.0  0.0   6620  3896 ?        R+   21:22   0:00 ps aux
sh-5.2$ exit
exit

$ hakoniwa run -v --config /etc/hakoniwa.d/firefox.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: /etc/hakoniwa.d/firefox.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/os/bare.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/os/freedesktop.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/device/dri.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/device/snd.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/dbus-session.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/dbus-system.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/pipewire.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/pulseaudio.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/wayland.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/socket/x11.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/network/mode/host.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/network/connect/autoproxy.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/network/connect/http.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/network/connect/https.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/device/v4l.toml
[2025-07-14T18:40:05Z DEBUG] CONFIG: Including /etc/hakoniwa.d/abstractions/filesystem/xdg-downloads.toml
[2025-07-14T18:40:05Z DEBUG] Unshare namespaces: CGROUP, MOUNT, PID, USER, UTS
[2025-07-14T18:40:05Z DEBUG] Mount:    root: /tmp/hakoniwa-4xtFNv
[2025-07-14T18:40:05Z DEBUG] Mount:   devfs: /dev
[2025-07-14T18:40:05Z DEBUG] Mount: bind_rw: /dev/dri -> /dev/dri
[2025-07-14T18:40:05Z DEBUG] Mount: bind_rw: /dev/snd -> /dev/snd
...
[2025-07-14T18:40:05Z DEBUG] Execve: "/usr/bin/firefox", []
...
```

More examples can be found in [hakoniwa-cli](https://github.com/souk4711/hakoniwa/tree/main/hakoniwa-cli).

### Rust Library

The code below is almost eq to `hakoniwa run -- sh`:

```rust
use hakoniwa::Container;

fn main() {
    _ = Container::new()        // Create Container with new namespaces via unshare
        .rootfs("/").unwrap()   // Mount necessary directories, e.g. `/bin`
        // .devfsmount("/dev")     // Mount `devfs` on `/dev`, it contains a minimal set of device files, like `/dev/null`
        // .tmpfsmount("/tmp")     // Mount `tmpfs` on `/tmp`
        // .setrlimit(..)          // Set resource limits
        // .cgroups_resources(..)  // Set cgroups resources
        // .landlock_ruleset(..)   // Set landlock ruleset
        // .seccomp_filter(..)     // Set seccomp filter
        .command("/bin/sh")     // Create Command
        .status()               // Execute
        .expect("failed to execute process within container");
}
```

More examples can be found in [hakoniwa](https://github.com/souk4711/hakoniwa/tree/main/hakoniwa).

### Executable supervisor for embedding applications

By default, a command's supervisor is forked from the calling application.
Long-lived runs can retain old host pages when that application rewrites its
memory. An embedding application can instead select a dedicated executable:

```rust,no_run
use hakoniwa::{Container, Supervisor};
use std::path::PathBuf;

fn main() -> hakoniwa::Result<()> {
    let helper = PathBuf::from("/path/to/supervisor");
    let status = Container::new()
        .rootfs("/")?
        .command("/bin/true")
        .supervisor(Supervisor::Image(helper))
        .status()?;
    assert!(status.success());
    Ok(())
}
```

The helper's complete entry point is:

```rust,no_run
fn main() {
    hakoniwa::supervise();
}
```

Build and distribute the host and helper together, using the same Hakoniwa
sources and features. The private frame guard detects selected mismatches; it
is not authentication or a stable cross-version protocol. The helper path
must refer to a trusted executable. It receives its command through inherited
startup pipes and is not intended for direct command-line use. The example
`cargo build -p hakoniwa --example supervisor` builds that entry point.

Both modes use the existing sandbox setup, Child ownership and status paths.
No helper is needed when using the default Fork mode. Closure commands remain
on that path; explicitly selecting Image for a closure returns an error.
The helper launch and frame exchange are synchronous and introduce no new
startup deadline. Applications opting in gain a fresh supervisor image at the
cost of one more executable to package and maintain.

## How It Works

![Implementation of Command::staus](https://github.com/souk4711/hakoniwa/raw/main/architecture.svg)

## Acknowledgements

- Special thanks to [bubblewrap](https://github.com/containers/bubblewrap).

## License

The CLI is licensed under the [GPL-3.0-only](https://github.com/souk4711/hakoniwa/blob/main/hakoniwa-cli/LICENSE).

The Library is licensed under the [LGPL-3.0-only WITH LGPL-3.0-linking-exception](https://github.com/souk4711/hakoniwa/blob/main/hakoniwa/LICENSE).
