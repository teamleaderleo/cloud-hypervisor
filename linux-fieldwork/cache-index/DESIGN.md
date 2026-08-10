# AArch64 cacheinfo index portability — design notes

Updated: 2026-08-10
Source generation: `a1fcb9f790616ac615f66de73be540b0b20844b1`
Owning Fieldwork issue: `teamleaderleo/linux-fieldwork#541`

## Current conclusion from source review

Linux ARM64 assigns cacheinfo/sysfs indices by cache **leaf**, while Cloud Hypervisor currently interprets those indices as fixed cache identities. A separate cache level consumes two leaves (Data then Instruction); a unified level consumes one. The current mapping therefore describes one representable topology correctly — split L1 data/instruction plus unified L2/L3 — and can assign valid host cache bytes to the wrong guest cache identity on other layouts.

FDT and PPTT also currently encode one particular guest cache model:

- split L1 Data and Instruction;
- unified L2;
- optional unified L3.

This means replacing `indexN` with a `(level, type)` lookup alone cannot faithfully represent unified L1 or split L2/L3. The first correction should distinguish **discovery correctness** from **guest representation support**.

## Preferred first candidate boundary

Read cache leaves by their sysfs `level` and `type`, then classify the host layout.

### Representable layout

Accept and map the leaves that the current FDT/PPTT model can describe:

- exactly one L1 Data leaf;
- exactly one L1 Instruction leaf;
- zero or one L2 Unified leaf;
- zero or one L3 Unified leaf.

Higher cache levels can be ignored for the current guest model after identity-aware discovery because they no longer shift the identities of L1-L3 entries.

Keep the existing missing-property policy from #8097 for a recognized leaf: absent optional scalar metadata remains zero/false; malformed-present metadata remains an error.

### Valid but currently unrepresentable layout

Examples:

- L1 Unified;
- L2 Data + L2 Instruction;
- L3 Data + L3 Instruction;
- duplicate or otherwise ambiguous leaves for one represented identity.

Return the existing cache-less result (`Ok(None)`) and emit one high-signal warning that host cache topology cannot be represented by the current guest cache model. FDT and PPTT already support the cache-less path.

This is preferable to copying a unified cache into both split fields or labelling an Instruction leaf as a Unified cache. It changes guest output from incorrect cache identity to omitted optional cache topology on unsupported layouts.

## Why omission is the smaller first correction

A generic cache-leaf graph would require coordinated redesign of:

- `CacheTopologyInfo`;
- FDT CPU/cache-node construction and `next-level-cache` links;
- PPTT cache-node type/level construction and hierarchy;
- sharing semantics for arbitrary leaves;
- tests for guest-visible topology across several valid host layouts.

That can be a later enhancement. #541 first needs a bounded correctness result: current representable layouts stay byte/field-equivalent; valid unrepresentable layouts stop being described incorrectly.

## Required discriminators for a candidate

1. **Current control:** split L1 + unified L2/L3 maps to the same cache values and sharing flags as current code.
2. **Unified L1:** recognized as valid-but-unrepresentable and produces cache-less output, with no L2/L3 bytes mislabelled as L1I/L2.
3. **Split L2:** recognized as valid-but-unrepresentable and produces cache-less output, with no L2I bytes mislabelled as L3.
4. **Higher unified level:** a representable L1-L3 layout plus L4 remains representable for L1-L3; L4 is ignored without shifting identity.
5. **Malformed `level`/`type`:** treated as a present malformed cache property error, consistent with #8097.
6. **Missing `level`/`type`:** verify the Linux sysfs contract before selecting fallback versus error. Do not guess.
7. **Clean rerun:** synthetic fixture directories leave no persistent state.

## Evidence needed before product code

The current test-only baseline must execute the control and both counterexamples against the exact #8666 + #8097 prerequisites. A passing counterexample means the current parser assigned bytes to a field whose intended identity disagrees with the fixture's sysfs `level`/`type`.

After that receipt, implement the classifier as a separate successor patch rather than changing the saturated #8097 bytes.

## Reopen / widen triggers

Widen to a generic cache graph only if:

- maintainers or an existing contract require passthrough for unified L1 or split higher levels;
- omission creates a concrete guest regression worse than the current misdescription;
- a natural reusable representation can serve both FDT and PPTT without duplicating topology logic.

## External-contact state

`false; none occurred`.
