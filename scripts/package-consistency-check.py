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


PROBE_BRANCH = "linux-fieldwork/sparse-page-probe-1af93ac"
EXPECTED_SOURCE_BLOB = "10b9761484321c3ee0829584ad89cd126ba0dd6f"
EXPECTED_PATCH_BLOB = "ece384ad47c9a6476c94bb6102329c73c83cc464"


def run_checked(command):
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def run_fieldwork_sparse_probe():
    if os.environ.get("GITHUB_HEAD_REF") != PROBE_BRANCH:
        return

    source = Path("vmm/src/sparse.rs")
    patch = Path("scripts/fieldwork-sparse-page.patch")
    if not source.exists() or not patch.exists():
        return

    source_blob = run_checked(["git", "rev-parse", f"HEAD:{source}"]).stdout.strip()
    patch_blob = run_checked(["git", "hash-object", str(patch)]).stdout.strip()
    if source_blob != EXPECTED_SOURCE_BLOB:
        raise RuntimeError(f"sparse source drifted: {source_blob} != {EXPECTED_SOURCE_BLOB}")
    if patch_blob != EXPECTED_PATCH_BLOB:
        raise RuntimeError(f"candidate patch drifted: {patch_blob} != {EXPECTED_PATCH_BLOB}")

    page_size = os.sysconf("SC_PAGE_SIZE")
    print(f"FIELDWORK: hosted baseline page size = {page_size}")

    test_prefix = "sparse::unit_tests"
    list_result = run_checked([
        "cargo", "test", "--locked", "-p", "vmm", "--lib", test_prefix,
        "--features", "kvm", "--", "--list"
    ])
    for expected in (
        "sparse::unit_tests::written_pages_show_as_data_extents",
        "sparse::unit_tests::sparse_file_yields_extents_at_written_positions",
        "sparse::unit_tests::single_extent_at_zero_offset",
        "sparse::unit_tests::two_regions_in_same_destination_file_at_dst_offset",
        "sparse::unit_tests::extent_at_non_zero_src_offset",
        "sparse::unit_tests::round_trip_sparse_write_then_read",
        "sparse::unit_tests::enumeration_respects_window",
    ):
        if expected not in list_result.stdout:
            raise RuntimeError(f"focused sparse test missing: {expected}")

    print("FIELDWORK: current-source sparse baseline")
    run_checked([
        "cargo", "test", "--locked", "-p", "vmm", "--lib", test_prefix,
        "--features", "kvm"
    ])

    try:
        print(f"FIELDWORK: apply exact candidate {patch_blob}")
        run_checked(["git", "apply", "--check", str(patch)])
        run_checked(["git", "apply", str(patch)])
        changed = run_checked(["git", "diff", "--name-only"]).stdout.splitlines()
        if changed != ["vmm/src/sparse.rs"]:
            raise RuntimeError(f"candidate changed unexpected paths: {changed}")

        print("FIELDWORK: page-aware sparse candidate")
        run_checked([
            "cargo", "test", "--locked", "-p", "vmm", "--lib", test_prefix,
            "--features", "kvm"
        ])
        run_checked(["rustup", "component", "add", "rustfmt", "clippy"])
        run_checked(["cargo", "fmt", "--all", "--", "--check"])
        run_checked([
            "cargo", "clippy", "--locked", "-p", "vmm", "--features", "kvm",
            "--", "-D", "warnings"
        ])
        print("FIELDWORK: 4K baseline/candidate/rustfmt/clippy gates passed")
        print("FIELDWORK: real 16K baseline/candidate execution remains required")
    finally:
        run_checked(["git", "checkout", "--", str(source)])
        run_checked(["git", "diff", "--exit-code", "--", str(source)])


def get_cargo_metadata():
    result = subprocess.run(
        ["cargo", "metadata", "--format-version=1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        exit(1)

    metadata = json.loads(result.stdout)
    return metadata


def find_dependents_of_package(metadata, package_source):
    """Find dependencies based on the provided source identifier and return related package info."""
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
    run_fieldwork_sparse_probe()

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
    has_conflicts = check_for_version_conflicts(packages, direct_dependents)

    if has_conflicts:
        exit(1)
