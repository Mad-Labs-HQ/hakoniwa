"""Refuse one syscall in a disposable command for native regression tests.

The caller must run this as a subprocess. The filter applies only here and to
the command executed here; it never changes the caller or the host kernel.
Requires Linux libseccomp and preserves ordinary syscall behavior otherwise.
"""

import ctypes
import os
import sys


def main() -> None:
    """Install the requested errno rule, then replace this process with a test."""
    name, encoded_errno, executable, *arguments = sys.argv[1:]
    error = int(encoded_errno)
    if not 1 <= error <= 4095:
        raise ValueError("seccomp errno must be between 1 and 4095")
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    number = library.seccomp_syscall_resolve_name(name.encode())
    if number < 0:
        raise ValueError("unknown syscall")
    context = library.seccomp_init(0x7FFF0000)
    if not context:
        raise RuntimeError("seccomp allocation failed")
    try:
        if library.seccomp_rule_add(context, 0x00050000 | error, number, 0) < 0:
            raise RuntimeError("seccomp rule failed")
        if library.seccomp_load(context) < 0:
            raise RuntimeError("seccomp load failed")
    finally:
        library.seccomp_release(context)
    os.execv(executable, [executable, *arguments])


if __name__ == "__main__":
    main()
