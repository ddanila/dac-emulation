# Native memory allocation after initial inventory

The separate `k7658-memory-growth-runtime` candidate adds an explicit diagnostic allocation API using normal memory registration, scope attachment and registered static vector storage. It does not replace the queued board runtime.

Two rounds add an unsigned 8-bit two-word memory and a signed 80-bit three-word memory with descending declared indices. Complete metadata and dense array inventories grow from one to five memories. Each allocation has a fresh increasing scope-object ID and distinct live handle, array and storage identities. All earlier rows remain exactly equal. Every new word retains its high X bits and alternating low bit; public indexed reads independently check values. Each new lazy cache has the correct parent and word links and changes no other payload. Original, disabled and enabled HDL continuation agrees. Invalid kind 2 refuses without changing the enabled inventory.

The first diagnostic attempt found that public lookup materialized the original memory cache after the initial image. The final fixture deliberately materializes that original cache before observation. The earlier failed attempt remains local at `build/keyboard-controller-analog/memory-growth`; this report retains the successful v2 capture. No comparison tolerance was relaxed.

Sixteen unsupported-array family runs and three native memory metadata/layout controls also pass on this exact new build. Four replay/rejection tests cover these results, a lost high payload bit, missing lazy allocation and a missing allocation event. This evidence does not qualify native destruction, address reuse, compact logging, natural dynamic-array allocation or operational board observation.
