# Native shutdown smoke control

An isolated candidate enables the native CHECK_WITH_VALGRIND final cleanup path and compiles with AddressSanitizer. Valgrind client annotations are deliberately no-ops, RUNNING_ON_VALGRIND is zero, and leak detection is disabled. This is not a Valgrind run or custom-pool access validation.

The hierarchical fixture includes two child scopes, wide/real/embedded-null parameters, static memories, asynchronous memory read ports, clocked writes to an index, and a monitor. Original-library and candidate-library runs use the same executable and produce identical complete output through CONTINUE and normal exit, with empty stderr. The retained configuration, cleanup source, Makefiles and linkage record supplement build and execution receipts.

This is a smoke control only. It does not explicitly populate every lazy observer registry, prove each destructor ran, test dangling handles, qualify board teardown, or check leaks. A first build failed because the compatibility header lacked RUNNING_ON_VALGRIND; a fresh second build succeeded. Its metadata finalization was repaired to accept generated preprocessor whitespace, without rebuilding or altering its binaries. Earlier local failed setup directories remain preserved.
