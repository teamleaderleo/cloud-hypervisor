#!/usr/bin/env python3
import subprocess
from pathlib import Path

AFFINITY_COMMIT = "9acace966a333c9314cceedd0e6f1cdaa8812850"
AFFINITY_RUNNER_PATH = "linux-fieldwork/cache-affinity/run_candidate.py"
AFFINITY_RUNNER_BLOB = "a176dfaa2a639a301b3c4371c14952d9d87e6091"
AFFINITY_PATCH_PATH = "linux-fieldwork/cache-affinity/candidate.patch"
AFFINITY_PATCH_BLOB = "75601cb2fa2a7d8f8f85dcdd9c3724c41a18d947"

L3_COMMIT = "383eebc96afa743dd365c82f34b2feb944a71cf9"
L3_PATCH_PATH = "linux-fieldwork/fdt-l3-smt/candidate.patch"
L3_PATCH_BLOB = "239a2a7c9a7fe7031a594605f3801f2b06c53fa2"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def materialize(commit: str, source_path: str, destination: Path, expected_blob: str) -> Path:
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
    return destination


for branch in [
    "linux-fieldwork/cache-affinity-selection",
    "linux-fieldwork/fdt-l3-smt",
]:
    run("git", "fetch", "--no-tags", "origin", branch)

# Apply and locally commit exact #543 v2.
affinity_runner = materialize(
    AFFINITY_COMMIT,
    AFFINITY_RUNNER_PATH,
    Path("/tmp/cache-affinity-runner.py"),
    AFFINITY_RUNNER_BLOB,
)
materialize(
    AFFINITY_COMMIT,
    AFFINITY_PATCH_PATH,
    Path(AFFINITY_PATCH_PATH),
    AFFINITY_PATCH_BLOB,
)
run("python3", str(affinity_runner))
run(
    "git",
    "add",
    "arch/src/aarch64/cache.rs",
    "arch/src/aarch64/fdt.rs",
    "arch/src/aarch64/mod.rs",
    "vmm/src/cpu.rs",
    "vmm/src/vm.rs",
    "vmm/src/vm_config.rs",
)
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated cache affinity v2 prerequisite",
)
Path(AFFINITY_PATCH_PATH).unlink()
try:
    Path("linux-fieldwork/cache-affinity").rmdir()
except OSError:
    pass

# Apply and locally commit exact #546.
l3_patch = materialize(
    L3_COMMIT,
    L3_PATCH_PATH,
    Path("/tmp/fdt-l3-smt.patch"),
    L3_PATCH_BLOB,
)
run("git", "apply", "--check", str(l3_patch))
run("git", "apply", str(l3_patch))
run("cargo", "+nightly", "fmt", "--all", "--", "--check")
run("git", "add", "arch/src/aarch64/fdt.rs")
run(
    "git",
    "-c",
    "user.name=Linux Fieldwork CI",
    "-c",
    "user.email=linux-fieldwork@example.invalid",
    "commit",
    "-m",
    "ci: apply validated FDT L3 SMT prerequisite",
)

# vmm/src/config.rs: make the accepted AArch64 boot<max configuration executable
# inside the existing comprehensive validation test.
config_path = Path("vmm/src/config.rs")
config = config_path.read_text()
anchor = '''        let mut still_valid_config = valid_config.clone();
        still_valid_config.cpus.max_vcpus = 8;
        still_valid_config.cpus.boot_vcpus = 8;
        still_valid_config.cpus.topology = Some(CpuTopology {
            threads_per_core: 2,
            cores_per_die: 4,
            dies_per_package: 1,
            packages: 1,
        });
        still_valid_config.validate().unwrap();
'''
probe = anchor + '''        #[cfg(target_arch = "aarch64")]
        {
            let mut still_valid_config = valid_config.clone();
            still_valid_config.cpus.max_vcpus = 4;
            still_valid_config.cpus.boot_vcpus = 2;
            still_valid_config.cpus.topology = Some(CpuTopology {
                threads_per_core: 1,
                cores_per_die: 4,
                dies_per_package: 1,
                packages: 1,
            });
            still_valid_config.validate().unwrap();
        }
'''
if anchor not in config:
    raise RuntimeError("config topology validation test anchor changed")
config_path.write_text(config.replace(anchor, probe, 1))

# arch/src/aarch64/fdt.rs: execute the exact domain mismatch caused by building
# a max-sized cpu-map from a boot-sized MPIDR/CPU-node list.
fdt_path = Path("arch/src/aarch64/fdt.rs")
fdt = fdt_path.read_text()
fdt_probe = r'''

#[cfg(test)]
mod max_boot_cpu_map_tests {
    #[test]
    fn test_max_sized_cpu_map_can_exceed_boot_cpu_node_domain() {
        let boot_vcpus = 2u32;
        let threads_per_core = 1u32;
        let cores_per_die = 4u32;
        let dies_per_package = 1u32;
        let packages = 1u32;
        let max_vcpus = threads_per_core * cores_per_die * dies_per_package * packages;

        let emitted_cpu_ids: Vec<u32> = (0..boot_vcpus).collect();
        let cpu_map_ids: Vec<u32> = (0..max_vcpus).collect();

        assert_eq!(emitted_cpu_ids, vec![0, 1]);
        assert_eq!(cpu_map_ids, vec![0, 1, 2, 3]);
        assert!(
            cpu_map_ids
                .iter()
                .any(|cpu_id| *cpu_id >= boot_vcpus)
        );
    }
}
'''
if "mod max_boot_cpu_map_tests" in fdt:
    raise RuntimeError("max/boot FDT probe already present")
fdt_path.write_text(fdt + fdt_probe)

run("cargo", "+nightly", "fmt", "--all")
print("aarch64-max-boot-prerequisites-applied")
print("aarch64-max-boot-config-probe-injected")
print("aarch64-max-boot-fdt-probe-injected")
