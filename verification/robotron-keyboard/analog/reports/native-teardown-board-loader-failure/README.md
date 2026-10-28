# Rejected board startup: VPI loader table interposition

The first integrated ASAN attempt aborts at startup, before the full transient or native teardown. The report identifies a global-buffer-overflow in check_callback_time while reading a callback time pointer. Its reported global begins at the ivlng module loader-table address but is attributed to system.vpi's larger startup table.

The retained ivlng symbol table places vlog_startup_routines at offset 0x80d0, watch.cb at 0x8168, and its time pointer at offset 0x8180. ASAN reports a read 0xb0 bytes after the startup-table address, exactly that pointer. This supports the module-symbol interposition diagnosis: the instrumented system table poisons neighboring uninstrumented bridge globals. The following candidate excludes only the fixed system loader table from global instrumentation; this failed run remains rejected. All capture receipts, the complete diagnostic, source identities and module symbols are retained.
