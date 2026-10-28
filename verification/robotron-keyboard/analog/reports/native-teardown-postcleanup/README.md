# Post-cleanup observer refusal

The fixture first populates and validates seven native inventories at simulation start and end. Its VPI unload destructor then calls those same observers after native root, code and pool cleanup, following the order in the exact candidate's retained lib_main.cc. All seven calls return -1 with zero output, and execution reaches POST_CLEANUP_RETURN. Original-library, disabled and enabled HDL output is identical; all processes exit successfully with empty stderr. Five replay/rejection tests pass.

The candidate is the exact ASAN runtime used by the populated-observer report. Its fixture loader table alone is excluded from ASAN global instrumentation to accommodate the required duplicate VPI export. Leak detection and Valgrind annotations remain disabled. This is safe post-cleanup refusal for this fixture, not evidence that registries are empty, every destructor ran, dangling handles are safe, or board teardown is qualified.

An initial local probe incorrectly required successful inventory construction after cleanup and exited on the first safe refusal. The retained revision instead captures every return code and byte count and requires all seven exact zero-output refusals. No runtime behavior or refusal gate was weakened.
