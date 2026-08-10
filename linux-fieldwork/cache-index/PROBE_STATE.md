# Cache-index portability probe state

Updated: 2026-08-10

Purpose: durable trigger/checkpoint for the test-only AArch64 cacheinfo index portability baseline.

- Canonical source: `a1fcb9f790616ac615f66de73be540b0b20844b1`
- Fieldwork issue: `teamleaderleo/linux-fieldwork#541`
- Internal carrier: `teamleaderleo/cloud-hypervisor#7`
- Product prerequisites: exact validated #8666 ACPI and #8097 cache-runtime-error candidates
- Probe scope: test-only changes after committing prerequisites locally
- Control: split L1 data/instruction, unified L2/L3
- Counterexamples: unified L1; split L2 with L3 shifted to index4
- External-contact state: `false; none occurred`

A passing counterexample means the current fixed sysfs-index mapping was observed assigning cache bytes to fields whose intended level/type differs from the sysfs `level`/`type` identity. It is evidence for the portability decision, not a product fix.
