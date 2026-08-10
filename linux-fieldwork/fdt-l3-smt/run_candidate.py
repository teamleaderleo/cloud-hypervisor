#!/usr/bin/env python3
import subprocess
from pathlib import Path

AFFINITY_COMMIT = "faae0e28627e9ebcbc7df3d3173ffe46f3e4baa4"
AFFINITY_RUNNER_PATH = "linux-fieldwork/cache-affinity/run_candidate.py"
AFFINITY_RUNNER_BLOB = "f983c0d2ff94621b58275e81fb48ea7ea73fe5df"
AFFINITY_PATCH_PATH = "linux-fieldwork/cache-affinity/candidate.patch"
AFFINITY_PATCH_BLOB = "57542277a76d84ed4bfca58aab871ef27f090beb"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def materialize(commit: str, source_path: str, destination: Path, expected_blob: str) -> None:
    content = subprocess.run(
        ["git", "show", f"{commit}:{source_path}"],
        check=True,
        capture_output=True,
    ).stdout
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    actual = output("git", "hash-object", str(destination))
    if actual != expected_blob:
        raise RuntimeError(
            f"{source_path}: expected blob {expected_blob}, found {actual}"
        )


run("git", "fetch", "--no-tags", "--depth=100", "origin", "linux-fieldwork/cache-affinity-selection")
runner = Path("/tmp/cache-affinity-runner.py")
materialize(AFFINITY_COMMIT, AFFINITY_RUNNER_PATH, runner, AFFINITY_RUNNER_BLOB)
materialize(AFFINITY_COMMIT, AFFINITY_PATCH_PATH, Path(AFFINITY_PATCH_PATH), AFFINITY_PATCH_BLOB)
run("python3", str(runner))

run(
    "git",
    "add",
    "arch/src/aarch64/cache.rs",
    "arch/src/aarch64/fdt.rs",
    "arch/src/aarch64/mod.rs",
    "vmm/src/cpu.rs",
    "vmm/src/vm.rs",
)
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated cache affinity prerequisite",
)
Path(AFFINITY_PATCH_PATH).unlink()
try:
    Path("linux-fieldwork/cache-affinity").rmdir()
except OSError:
    pass

fdt_path = Path("arch/src/aarch64/fdt.rs")
fdt = fdt_path.read_text()

create_cpu_anchor = "fn create_cpu_nodes(\n"
helper = '''fn l3_package_id(cpu_id: usize, threads_per_core: u16, cores_per_package: u16) -> u32 {
    let logical_cpus_per_package = u32::from(threads_per_core) * u32::from(cores_per_package);
    cpu_id as u32 / logical_cpus_per_package
}

'''
if create_cpu_anchor not in fdt:
    raise RuntimeError("create_cpu_nodes anchor changed")
fdt = fdt.replace(create_cpu_anchor, helper + create_cpu_anchor, 1)

old = "let package_id: u32 = cpu_id as u32 / cores_per_package as u32;"
new = "let package_id = l3_package_id(cpu_id, threads_per_core, cores_per_package);"
if old not in fdt:
    raise RuntimeError("L3 package selector anchor changed")
fdt = fdt.replace(old, new, 1)

tests = r'''

#[cfg(test)]
mod l3_package_id_tests {
    use super::l3_package_id;

    #[test]
    fn test_l3_package_id_single_thread_control() {
        let package_ids: Vec<u32> = (0..4)
            .map(|cpu_id| l3_package_id(cpu_id, 1, 2))
            .collect();
        assert_eq!(package_ids, vec![0, 0, 1, 1]);
    }

    #[test]
    fn test_l3_package_id_accounts_for_smt_threads() {
        let package_ids: Vec<u32> = (0..8)
            .map(|cpu_id| l3_package_id(cpu_id, 2, 2))
            .collect();
        assert_eq!(package_ids, vec![0, 0, 0, 0, 1, 1, 1, 1]);
    }
}
'''
if "mod l3_package_id_tests" in fdt:
    raise RuntimeError("L3 package ID candidate tests already present")
fdt_path.write_text(fdt + tests)
run("cargo", "+nightly", "fmt", "--all")
print("fdt-l3-smt-prerequisites-applied")
print("fdt-l3-smt-candidate-applied")
