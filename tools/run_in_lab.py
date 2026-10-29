"""Start full-chain replay from read-only inputs, without mounting a fork checkout.

The host prepares the archive separately. This entrypoint runs inside the
native Linux lab as its unprivileged application user.
"""

import subprocess
import sys

subprocess.run(
    [
        sys.executable,
        "/inputs/harness/verify_registry.py",
        "--inputs",
        "/inputs",
        "--out",
        "/results/registry",
    ],
    check=True,
)
