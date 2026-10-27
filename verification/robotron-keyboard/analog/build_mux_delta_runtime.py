#!/usr/bin/env python3
"""Build full-scan lossless mux cache differences and complete wrapper records."""
import argparse
import json
from pathlib import Path
import subprocess
import build_display_association as base
from ttl7406_probe import sha


def build(archive,out,bison,jobs):
    runtime,display=base.RUNTIME_PATCHES,base.DISPLAY_PATCHES
    try:
        base.RUNTIME_PATCHES=runtime+('icarus-single-display-runtime.patch','icarus-executing-wrapper-link.patch',
                                     'icarus-executing-event.patch','icarus-value-callback-observer.patch','icarus-startup-callback-observer.patch','icarus-assignment-observer.patch','icarus-primitive-observer.patch','icarus-island-observer.patch','icarus-island-queue.patch','icarus-island-filter.patch','icarus-thread-observer.patch','icarus-thread-queue.patch','icarus-wait-observer.patch','icarus-thread-lifecycle.patch','icarus-code-binding.patch','icarus-scope-observer.patch','icarus-code-operands.patch','icarus-array-observer.patch','icarus-array-compact.patch','icarus-net-observer.patch','icarus-net-delta.patch','icarus-net-types.patch','icarus-wire-observer.patch','icarus-wire-delta.patch','icarus-signal-observer.patch','icarus-signal-delta.patch','icarus-mux-observer.patch','icarus-mux-delta.patch')
        base.DISPLAY_PATCHES=display+('icarus-single-display-module.patch',)
        base.build(archive,out,bison,jobs)
    finally:
        base.RUNTIME_PATCHES,base.DISPLAY_PATCHES=runtime,display
    exports=subprocess.check_output(['nm','-g',str(out/'vvp/libvvp.so')],text=True)
    for symbol in ('robotron_vvp_island_inventory','robotron_vvp_island_toggle','robotron_vvp_island_queue_inventory','robotron_vvp_island_queue_toggle','robotron_vvp_island_filter_inventory','robotron_vvp_island_filter_toggle','robotron_vvp_thread_inventory','robotron_vvp_thread_toggle','robotron_vvp_thread_compact_inventory','robotron_vvp_thread_queue_inventory','robotron_vvp_thread_queue_toggle','robotron_vvp_wait_inventory','robotron_vvp_wait_toggle','robotron_vvp_thread_code_inventory','robotron_vvp_code_identity','robotron_vvp_scope_inventory','robotron_vvp_scope_toggle','robotron_vvp_code_operand_reference','robotron_vvp_code_operand_inventory','robotron_vvp_code_operand_toggle','robotron_vvp_array_inventory','robotron_vvp_array_toggle','robotron_vvp_array_compact_inventory','robotron_vvp_net_inventory','robotron_vvp_net_toggle','robotron_vvp_net_reference','robotron_vvp_net_delta_inventory','robotron_vvp_net_types','robotron_vvp_wire_inventory','robotron_vvp_wire_toggle','robotron_vvp_wire_reference','robotron_vvp_wire_delta_inventory','robotron_vvp_signal_inventory','robotron_vvp_signal_toggle','robotron_vvp_signal_reference','robotron_vvp_signal_delta_inventory','robotron_vvp_mux_inventory','robotron_vvp_mux_toggle','robotron_vvp_mux_queue','robotron_vvp_mux_reference','robotron_vvp_mux_delta_inventory'):
        if symbol not in exports:raise ValueError('Missing primitive API')
    path=out/'build.json';r=json.loads(path.read_text())
    r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs'].update({n:sha(out/n) for n in ('vvp/vpi_priv.h','vvp/vvp_vpi_callback.h')})
    for name in ('schedule.cc','schedule.h','logic.cc','logic.h','part.cc','part.h','vvp_island.cc','vvp_island.h','island_tran.cc','vvp_net.h','vvp_net_sig.h','vvp_net_sig.cc','vthread.cc','event.h','event.cc','codes.cc','codes.h','vpi_scope.cc','array.cc','array_common.cc','array_common.h','vvp_net.cc','vpi_callback.cc'):r['outputs']['vvp/'+name]=sha(out/'vvp'/name)
    r['scope']='Adds immutable-reference mux cache splices and full queued/executing wrapper rows on every frame. Adds all allocated MUXZ cache/select/run/pending fields and typed queued/executing wrapper bindings; other logic families remain separate. Includes per-signal fixed-reference splices with complete native scans. Includes initialized static signal storage, assignment masks/links and flags; other signal subclasses refuse observation. Includes full-scan lossless per-filter wire splice differences against a fixed reference; no dirty-state shortcuts. Includes full-scan fixed-reference graph deltas, including newly allocated nodes. Includes net allocation, binding and tagged-port observations with restored faults; payload contents remain separate. Includes static four-state array storage, ranges, existing word-handle cache links and independently registered read-port state. Automatic/aliased/other-family storage and array callbacks fail closed. Word/address/link/cache faults restore without invoking propagation setters. Requires native controls and board integration; destination net/fanout contents and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
