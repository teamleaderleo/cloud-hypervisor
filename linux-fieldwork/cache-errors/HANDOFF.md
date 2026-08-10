# Linux Fieldwork handoff — AArch64 cache discovery errors

Updated: 2026-08-10
State: STRONG CANDIDATE, CURRENT ERROR-PROPAGATION BOUNDARY SATURATED
Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Validated carrier head: `044a728ddf5d9dbb00eba04a6df6679e84521441`
Branch: `linux-fieldwork/cache-runtime-errors`
Canonical issue: `cloud-hypervisor/cloud-hypervisor#8097`
Internal record: `teamleaderleo/linux-fieldwork#499`
Prerequisite: exact validated #8666 ACPI candidate from `0a2f55acbd23b7f44899a69132a4236ef9240027`

## TL;DR

AArch64 cache discovery now has a bounded candidate that preserves the existing missing-data fallback while turning present-but-unusable host cache metadata into ordinary errors. The same cache error propagates through both consumers found by cross-context review: PPTT/ACPI and AArch64 FDT system setup.

The exact two-patch successor passes seven synthetic AArch64 cache fixtures under qemu-user, an immediate clean rerun, nightly rustfmt, focused AArch64 Clippy, AArch64 KVM and MSHV compilation, x86_64 KVM regression compilation, and automatic stored/generated patch byte equality.

The fixed sysfs `index0..index3` cache identification remains a separate portability question. It is deliberately excluded from this #8097 candidate.

## Source boundary

Exact canonical source blobs guarded by the runner:

- `arch/src/aarch64/cache.rs`: `9200c59627beba0e6366b5105d2fe51a312efaed`
- `arch/src/aarch64/fdt.rs`: `887d9edfe02056ab2567e4252fb6172236e1f770`
- `arch/src/aarch64/mod.rs`: `c53e4829b48c2bcd294642f86e501a6b85dfe680`
- `vmm/src/cpu.rs`: `5d9499878b04f7c0fb53cece5768988ceb439d25`
- `vmm/src/acpi.rs`: `6ac7666ebdc49c67fbc6233c135e8645f7e64e0f`
- `vmm/src/vm.rs`: `12a9fe0ad7068df7b26082b32de65d6f54b33d04`

The runner also fetches the immutable validated #8666 carrier commit `0a2f55acbd23b7f44899a69132a4236ef9240027`, extracts `linux-fieldwork/acpi-errors/candidate.patch`, requires blob `034cebd92cf31e3b415cdd3d205035b96cd9c1fb`, applies it, verifies nightly formatting, and commits only that prerequisite locally before applying the #8097 successor. The final successor diff therefore stays distinct from the prerequisite.

## Kernel contract and compatibility policy

Linux cacheinfo exports `coherency_line_size` and `number_of_sets` as decimal unsigned values. `size` is cache size in kB and current kernel code emits `<number>K`. `shared_cpu_list` lists logical CPUs sharing the cache. Several scalar cache attributes are omitted when the kernel has no corresponding value.

The candidate preserves that useful absence distinction:

1. missing cache root -> `Ok(None)` and the existing cache-less behavior;
2. missing individual property (`NotFound`) -> existing zero/false fallback;
3. other property I/O failure -> typed error carrying path and source;
4. present malformed decimal -> typed parse error carrying path and source;
5. malformed cache-size suffix -> typed format error;
6. checked byte-size overflow -> typed overflow error;
7. valid metadata -> unchanged cache values and topology generation.

Direct reads with `NotFound` classification replace the old `Path::exists()` followed by `read_to_string()`, eliminating that check/read race.

## Error paths

### PPTT / ACPI

```text
cache sysfs read / parse error
        ↓
arch::aarch64::cache::Error
        ↓
read_cache_topology() Result<Option<_>>
        ↓
CpuManager::create_pptt() Result
        ↓
cpu::Error::CacheTopology
        ↓
acpi::Error::ProcessorTopology
        ↓
VM CreatingAcpiTables
```

### FDT

```text
cache sysfs read / parse error
        ↓
arch::aarch64::cache::Error
        ↓
create_cpu_nodes()
        ↓
fdt::Error::CacheTopology
        ↓
aarch64::Error::SetupFdt
        ↓
VM boot Result
```

The FDT caller was discovered during adjacent-context review after the first PPTT-only design pass. Unrelated FDT invariants such as `FdtWriter::new().unwrap()` remain outside #8097.

## Exact product representation

The successor has two stored product patches:

- `linux-fieldwork/cache-errors/candidate.patch` — exact parser/error/test diff for `arch/src/aarch64/cache.rs`;
- `linux-fieldwork/cache-errors/propagation.patch` — exact propagation diff for `arch/src/aarch64/fdt.rs`, `arch/src/aarch64/mod.rs`, `vmm/src/acpi.rs`, and `vmm/src/cpu.rs`.

Temporary formatting, fixture-Clippy, FDT, and ACPI-Clippy patch layers used during refinement were removed after a complete semantic green. The stored two-patch representation was rematerialized from that run's generated artifact.

Product scope:

- parser patch: `arch/src/aarch64/cache.rs`, 305 insertions / 108 deletions;
- propagation patch: four files, 28 insertions / 10 deletions;
- combined successor scope: five files, 333 insertions / 118 deletions, with most parser growth coming from deterministic tests and typed error plumbing.

## Final focused evidence

Validated carrier head: `044a728ddf5d9dbb00eba04a6df6679e84521441`
Focused run: `31351617608`
Candidate job: `93343416995`
Artifact: `9049185049`
Artifact digest: `sha256:810949828cb8d1a0fd8816f6390acf15a5b8f339f08e94d3561513edd94388ff`

Exact patch digests:

- parser stored/generated: `sha256:6b521032579139478e272d39f5fee89e004bbaf8cea97ef0c68f4c1e200ceb67`
- propagation stored/generated: `sha256:9eadc8528c391a59c40f5507b37487fb8a528bf1a0b5f95d8c0ce961541107f5`

The artifact's `candidate-sha256.txt` records each stored patch and its generated `/tmp` counterpart with the same digest. Reviewed, applied, executed, compiled, and retained successor bytes are therefore identical.

All final gates passed:

- exact canonical source blob checks;
- exact immutable ACPI prerequisite identity and application;
- exact five-file successor scope and `git diff --check`;
- nightly rustfmt;
- seven named AArch64 cache fixtures executed under qemu-user;
- immediate clean fixture rerun;
- focused AArch64 Clippy for `arch` and `vmm` with warnings denied;
- AArch64 KVM `vmm` compile;
- AArch64 MSHV `vmm` compile;
- x86_64 KVM regression compile;
- generated parser and propagation diffs;
- automatic `cmp` against both stored product patches;
- SHA-256 receipt and artifact upload.

The seven executed fixtures prove:

- absent cache root returns `None`;
- present root with absent leaf properties preserves zero/false defaults;
- valid `32K`, decimal line/set values, and a shared CPU list produce expected values;
- malformed cache-size suffix returns `InvalidCacheSize`;
- malformed decimal returns `ParseCacheProperty`;
- a deterministic non-`NotFound` read failure returns `ReadCacheProperty`;
- kB-to-byte overflow returns `CacheSizeOverflow`.

## Failure ownership learned during refinement

Red runs were classified before product conclusions:

- initial AArch64 harness omitted a hypervisor backend and failed to compile before qemu-user execution; adding KVM fixed the harness;
- an early carrier accidentally embedded propagation text into the parser patch; it was split before product evidence was accepted;
- nightly rustfmt found the exact import and wrapping differences hidden by hand-written patch text;
- focused Clippy found test-only absolute `std::env` / `std::process` paths and then an absolute `crate::cpu::Error` path in the ACPI wrapper; both were repaired in project style;
- two temporary patch revisions had malformed or mismatched hunk context and stopped in `git apply` before semantic gates;
- after the complete semantic green, generated artifact bytes replaced the temporary patch stack and the final convergence run passed automatic byte equality.

Each failure owner was repaired independently; a harness/carrier red was never treated as a product failure.

## Adjacent portability question kept separate

Current Cloud Hypervisor cache helpers identify cache levels through fixed sysfs indices:

- `index0` -> L1D
- `index1` -> L1I
- `index2` -> L2
- `index3` -> L3

Linux AArch64 assigns cacheinfo indices from discovered level/type order: a separate level contributes data then instruction entries; a unified level contributes one entry. The fixed mapping therefore fits the common L1D/L1I plus unified L2/L3 arrangement but can shift for unified L1 or differently split levels.

That can change which cache Cloud Hypervisor describes and deserves its own portability investigation. It changes the semantic question beyond #8097's runtime-error boundary, so it remains separate.

## Reopen triggers

Reopen this candidate if:

- any guarded source blob changes;
- a canonical #8097 fix appears;
- an absent cache property is shown to require an error instead of the current compatibility fallback;
- a valid kernel cacheinfo value rejected by the parser is demonstrated;
- a supported backend/boot path shows a propagation or compile difference outside the current gates.

Treat cache-index identification as a successor even if this candidate remains stable.

## Current recommendation

Keep the candidate error policy and both propagation paths. Keep missing metadata as fallback. Keep the exact two-patch carrier and byte-equality gates. Further changes to #8097 should require a concrete counterexample or source freshness event.

## External-contact state

`false; none occurred`.
