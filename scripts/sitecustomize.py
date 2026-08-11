# Copyright © 2026 Contributors to the Cloud Hypervisor project
#
# SPDX-License-Identifier: Apache-2.0

"""Run the Linux Fieldwork common-SMBIOS-model probe in package consistency."""

import os
import subprocess
from pathlib import Path


BRANCH = "linux-fieldwork/smbios-model-probe-1af93ac"
PATCH_BLOB = "2b00e4444b72153306b45d74e4d5fefadca6a91a"
SOURCE_BLOBS = {
    "arch/src/lib.rs": "7e60a406bd8526bd28eaf591931661038d33f840",
    "arch/src/x86_64/smbios.rs": "2878ac3f5ff8f3eee65af5a046a269112c06b943",
    "vmm/src/vm_config.rs": "3cea9e18ab630517d98206fa4eb70ce16359166d",
}


def run(command, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def probe():
    if os.environ.get("GITHUB_HEAD_REF") != BRANCH:
        return

    patch = Path("scripts/fieldwork-smbios-model.patch")
    patch_blob = run(["git", "hash-object", str(patch)]).stdout.strip()
    if patch_blob != PATCH_BLOB:
        raise RuntimeError(f"SMBIOS model patch drifted: {patch_blob} != {PATCH_BLOB}")

    for path, expected in SOURCE_BLOBS.items():
        actual = run(["git", "rev-parse", f"HEAD:{path}"]).stdout.strip()
        if actual != expected:
            raise RuntimeError(f"source drifted for {path}: {actual} != {expected}")

    print("FIELDWORK: exact current SMBIOS model sources confirmed", flush=True)
    print("FIELDWORK: x86 SMBIOS baseline", flush=True)
    run(["cargo", "test", "--locked", "-p", "arch", "--lib", "smbios", "--features", "kvm"])

    try:
        run(["git", "apply", "--check", str(patch)])
        run(["git", "apply", str(patch)])
        if not Path("arch/src/smbios.rs").exists():
            raise RuntimeError("common arch/src/smbios.rs was not created")
        changed = set(run(["git", "diff", "--name-only"]).stdout.splitlines())
        expected_changed = {
            "arch/src/lib.rs",
            "arch/src/x86_64/smbios.rs",
            "vmm/src/vm_config.rs",
        }
        if changed != expected_changed:
            raise RuntimeError(f"unexpected tracked product diff: {sorted(changed)}")

        print("FIELDWORK: x86 SMBIOS candidate tests", flush=True)
        run(["cargo", "test", "--locked", "-p", "arch", "--lib", "smbios", "--features", "kvm"])
        run(["cargo", "check", "--locked", "-p", "vmm", "--features", "kvm"])

        print("FIELDWORK: AArch64 common-model compile", flush=True)
        run(["rustup", "target", "add", "aarch64-unknown-linux-gnu"])
        run([
            "cargo", "check", "--locked", "-p", "vmm",
            "--target", "aarch64-unknown-linux-gnu",
            "--no-default-features", "--features", "kvm",
        ])

        run(["rustup", "component", "add", "rustfmt", "clippy"])
        run(["cargo", "fmt", "--all", "--", "--check"])
        run([
            "cargo", "clippy", "--locked", "-p", "arch", "-p", "vmm",
            "--features", "kvm", "--", "-D", "warnings",
        ])
        print("FIELDWORK: common SMBIOS model x86/AArch64 gates passed", flush=True)
    finally:
        for path in SOURCE_BLOBS:
            run(["git", "checkout", "--", path], check=False)
        Path("arch/src/smbios.rs").unlink(missing_ok=True)


probe()
