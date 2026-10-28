# Native parameter destruction and same-address reconstruction

The separate candidate adds observer deregistration to the actual binary, real and string parameter destructors before native name/payload teardown. It uses the existing type-independent scope-registration invalidation helper, whose historical export name is `robotron_vvp_memory_forget`. Scope-object IDs retain the monotonic counter from the memory lifecycle candidate.

Two rounds construct, observe, destroy and reconstruct all three exact parameter classes in one reserved object buffer. Three inventories (parameter payload, scope metadata and object references) refuse the deliberately stale scope entry without output after each destruction: 18 refusals. Removing that entry restores all baseline inventory bytes. The six placements receive fresh IDs 5–10 at the same native handle address. Full 80-bit X-bearing values, real storage and embedded-null strings are verified, together with independent public VPI reads and original/disabled/enabled HDL continuation.

The object buffer is kept reserved for deterministic placement construction. This is not a claim about allocator-dependent reuse after freeing the buffer. The parameters are test-owned and have no compiled references. Full graph teardown, external dangling VPI handles, unsupported subclass destruction and operational deletion remain unqualified. Existing continuous board campaigns keep their pinned runtimes.

Same-build parameter class, parameter growth, memory lifecycle and array-family regressions pass. Four replay/rejection tests cover all reports, missing refusal, reused object identity and a lost embedded-null byte.
