# Linux Fieldwork handoff — AArch64 cache discovery errors

Updated: 2026-08-10
State: ACTIVE DESIGN / EXECUTION HARNESS PROBE
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Branch: `linux-fieldwork/cache-runtime-errors`
Canonical issue: `cloud-hypervisor/cloud-hypervisor#8097`
Internal record: `teamleaderleo/linux-fieldwork#499`
Prerequisite boundary: validated ACPI error candidate from `teamleaderleo/linux-fieldwork#444`

## TL;DR

Current AArch64 cache discovery treats an absent cache sysfs root or absent property as missing cache information, but it panics when a present property cannot be read or parsed. The kernel cacheinfo ABI makes that distinction useful: several attributes may be absent when the kernel has no value, while present scalar attributes have defined textual forms.

The candidate direction is to preserve absent metadata as the existing zero/false or cache-less fallback, return errors for malformed-present metadata and non-`NotFound` I/O failures, and propagate those errors through `CpuManager::create_pptt()` into the already-proven ACPI `Result` path.

Before product work, prove that hosted CI can execute AArch64 unit tests under qemu-user. Compile-only evidence is insufficient for malformed/missing synthetic fixtures.

## Source ownership

Exact current blobs:

- `arch/src/aarch64/cache.rs`: `9200c59627beba0e6366b5105d2fe51a312efaed`
- `vmm/src/cpu.rs`: `5d9499878b04f7c0fb53cece5768988ceb439d25`
- prerequisite ACPI source blob before #444 candidate: `vmm/src/acpi.rs` `6ac7666ebdc49c67fbc6233c135e8645f7e64e0f`

Current panic-producing cache operations are `fs::read_to_string(...).expect(...)`, decimal `parse().unwrap()`, and cache-size slicing/parsing after a path existence check.

`CpuManager::create_pptt()` currently returns `PPTT`; it calls `read_cache_topology()`, and `None` becomes the default cache-less `CacheTopologyInfo`. Preserve that compatibility behavior.

## Kernel contract reviewed

Current Linux cacheinfo sysfs exports:

- `coherency_line_size` and `number_of_sets` as decimal unsigned integers;
- `size` as `<number>K` from the kernel implementation, with the ABI describing the value as total cache size in kB;
- `shared_cpu_list` as the logical CPU list sharing the cache.

The kernel only exposes several scalar attributes when their corresponding cacheinfo values are available/nonzero. Therefore an absent leaf property remains a legitimate "unknown/unavailable" case and should retain the current zero/false fallback.

## Candidate error policy

1. Missing cache root: `Ok(None)` plus the existing warning.
2. Missing individual property (`NotFound`): preserve zero/false fallback.
3. Other property I/O failure: return an error with the property path and source error.
4. Present malformed decimal property: return a parse error with path context.
5. Present malformed cache size or checked kB-to-byte overflow: return an error.
6. Valid properties: preserve current values and PPTT generation.

Prefer direct reads with `NotFound` classification over `Path::exists()` followed by a read, removing the current check/read race.

## Proposed call chain

```text
cache sysfs read/parse error
        ↓
arch::aarch64::cache::Error
        ↓
read_cache_topology() Result<Option<_>>
        ↓
CpuManager::create_pptt() Result
        ↓
ACPI error boundary from #444
        ↓
VM boot Result
```

Keep this as a separate successor patch. Do not widen the stabilized #444 product candidate.

## Test plan

Use a helper that accepts a cache root path and synthetic disposable directory fixtures. Required discriminators:

- absent cache root -> `Ok(None)`;
- present root with missing optional property -> zero/false fallback;
- valid `32K` size + decimal line/set values -> expected bytes/integers;
- malformed size / malformed decimal -> typed error;
- non-`NotFound` read failure -> typed I/O error if a deterministic fixture is practical.

The first hosted probe is only to prove AArch64 test execution under qemu-user. No product claim should depend on that probe until an exact candidate and named tests run.

## Adjacent review boundary

The current helpers assume fixed sysfs index positions (`index0` L1D, `index1` L1I, `index2` L2, `index3` L3). That is a separate semantic question from #8097's panic/error requirement. Keep it visible and investigate independently before deciding whether it deserves its own carrier; do not silently fold it into the runtime-error patch.

## External-contact state

`false; none occurred`.
