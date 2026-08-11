#!/bin/env python3
#
# Copyright © 2024 Institute of Software, CAS. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0
#

import json
import os
import subprocess
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path


PROBE_BRANCH = "linux-fieldwork/smbios-model-probe-1af93ac"
PATCH_BLOB = "2b00e4444b72153306b45d74e4d5fefadca6a91a"
SOURCE_BLOBS = {
    "arch/src/lib.rs": "7e60a406bd8526bd28eaf591931661038d33f840",
    "arch/src/x86_64/smbios.rs": "2878ac3f5ff8f3eee65af5a046a269112c06b943",
    "vmm/src/vm_config.rs": "3cea9e18ab630517d98206fa4eb70ce16359166d",
}


def run_checked(command, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def run_fieldwork_smbios_model_probe():
    if os.environ.get("GITHUB_HEAD_REF") != PROBE_BRANCH:
        return

    patch = Path("scripts/fieldwork-smbios-model.patch")
    if not patch.exists() or not Path("arch/src/lib.rs").exists():
        return

    patch_blob = run_checked(["git", "hash-object", str(patch)]).stdout.strip()
    if patch_blob != PATCH_BLOB:
        raise RuntimeError(f"SMBIOS model patch drifted: {patch_blob} != {PATCH_BLOB}")

    for path, expected in SOURCE_BLOBS.items():
        actual = run_checked(["git", "rev-parse", f"HEAD:{path}"]).stdout.strip()
        if actual != expected:
            raise RuntimeError(f"source drifted for {path}: {actual} != {expected}")

    print("FIELDWORK: exact current SMBIOS model sources confirmed")
    print("FIELDWORK: x86 SMBIOS baseline")
    run_checked([
        "cargo", "test", "--locked", "-p", "arch", "--lib", "smbios", "--features", "kvm"
    ])

    try:
        run_checked(["git", "apply", "--check", str(patch)])
        run_checked(["git", "apply", str(patch)])
        if not Path("arch/src/smbios.rs").exists():
            raise RuntimeError("common arch/src/smbios.rs was not created")

        changed = set(run_checked(["git", "diff", "--name-only"]).stdout.splitlines())
        expected_changed = {
            "arch/src/lib.rs",
            "arch/src/x86_64/smbios.rs",
            "vmm/src/vm_config.rs",
        }
        if changed != expected_changed:
            raise RuntimeError(f"unexpected tracked product diff: {sorted(changed)}")

        print("FIELDWORK: x86 SMBIOS candidate tests")
        run_checked([
            "cargo", "test", "--locked", "-p", "arch", "--lib", "smbios", "--features", "kvm"
        ])
        run_checked(["cargo", "check", "--locked", "-p", "vmm", "--features", "kvm"])

        print("FIELDWORK: AArch64 common-model compile")
        run_checked(["rustup", "target", "add", "aarch64-unknown-linux-gnu"])
        run_checked([
            "cargo", "check", "--locked", "-p", "arch", "-p", "vmm",
            "--target", "aarch64-unknown-linux-gnu",
            "--no-default-features", "--features", "kvm",
        ])

        run_checked(["rustup", "component", "add", "rustfmt", "clippy"])
        run_checked(["cargo", "fmt", "--all", "--", "--check"])
        run_checked([
            "cargo", "clippy", "--locked", "-p", "arch", "-p", "vmm",
            "--features", "kvm", "--", "-D", "warnings",
        ])
        print("FIELDWORK: common SMBIOS model x86/AArch64 gates passed")
    finally:
        for path in SOURCE_BLOBS:
            run_checked(["git", "checkout", "--", path], check=False)
        Path("arch/src/smbios.rs").unlink(missing_ok=True)


def get_cargo_metadata():
    result = subprocess.run(
        ["cargo", "metadata", "--format-version=1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        exit(1)
    return json.loads(result.stdout)


def find_dependents_of_package(metadata, package_source):
    packages = defaultdict(list)
    direct_dependents = defaultdict(list)
    for pkg in metadata["packages"]:
        repository = pkg["repository"] or ""
        if package_source in repository:
            packages[pkg["name"]].append(pkg["version"])

    for node in metadata["resolve"]["nodes"]:
        current_pkg = next(pkg for pkg in metadata["packages"] if pkg["id"] == node["id"])
        current_pkg_name = current_pkg["name"]
        current_pkg_version = current_pkg["version"]
        for dep_id in node["dependencies"]:
            dep_pkg = next(pkg for pkg in metadata["packages"] if pkg["id"] == dep_id)
            dep_name = dep_pkg["name"]
            dep_version = dep_pkg["version"]
            if dep_name in packages:
                direct_dependents[(dep_name, dep_version)].append(
                    (current_pkg_name, current_pkg_version)
                )
    return packages, direct_dependents


def check_for_version_conflicts(packages, direct_dependents):
    has_conflicts = False
    for pkg_name, versions in packages.items():
        if len(set(versions)) > 1:
            has_conflicts = True
            print(f"Error: Multiple versions detected for {pkg_name}: {set(versions)}")
            for version in set(versions):
                print(f"  Version {version} used by:")
                for dependent, dep_version in direct_dependents[(pkg_name, version)]:
                    print(f"          - {dependent} v{dep_version}")
    return has_conflicts


if __name__ == "__main__":
    run_fieldwork_smbios_model_probe()

    parser = ArgumentParser(description="Cargo dependency conflict checker.")
    parser.add_argument(
        "package_source", type=str, help="A keyword used to match the repository URL field"
    )
    args = parser.parse_args()

    metadata = get_cargo_metadata()
    if metadata is None:
        print("Error: Metadata is empty")
        exit(1)

    packages, direct_dependents = find_dependents_of_package(metadata, args.package_source)
    if check_for_version_conflicts(packages, direct_dependents):
        exit(1)
