# Guarded unsupported-parameter recovery API

The diagnostic API owns only the unsupported parameter it creates through the existing class factory. It records the unique new scope owner, verifies the exact diagnostic subclass, and separately supports native virtual destruction and stale-entry detachment. Invalid operations, wrong kinds, premature detachment and duplicate allocation refuse. No arbitrary handle can be supplied for deletion.

Nine native baseline/disabled/enabled runs exercise two recovery rounds for each binary/real/string family through this API. Six unsupported and six subsequent supported parameters are destroyed; all three observers reject stale entries, and detachment restores every original inventory byte. Supported payloads include full wide X bits, real storage and embedded-null strings. Original HDL continuation matches. Same-build parameter lifecycle, class-admission and memory-layout regressions pass. Three replay/rejection tests pass.

This prepares the separate combined-board recovery candidate. It does not qualify arbitrary deletion, dangling external VPI handles, compiled references, allocator reuse or full graph teardown.
