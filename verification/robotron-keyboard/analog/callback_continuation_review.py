#!/usr/bin/env python3
"""Retain a manually reviewed continuation argument for pinned pthread callbacks.

This is a source argument with freshness checks, not a C/C++ dataflow verifier
or a proof of rollback, object lifetime safety, or source-to-binary equivalence.
"""
import argparse,json
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_identity import VPI_SOURCE,identity_vpi
HERE=Path(__file__).resolve().parent


def excerpt(text,start,end):
    if text.count(start)!=1:raise ValueError('Ambiguous source boundary')
    begin=text.index(start);finish=text.index(end,begin)
    return text[begin:finish]


def assess(vpi,identity_build,icarus,ngspice):
    if sha(vpi)!=VPI_SOURCE:raise ValueError('Changed timing-audited VPI source')
    source=vpi.read_text()
    if (identity_build/'vpi.c').read_text()!=identity_vpi(source):raise ValueError('Unexpected identity VPI modification')
    for root in (identity_build,icarus):
        receipt=json.loads((root/'build.json').read_text())
        for name,digest in receipt['sources'].items():
            dependency=Path(name) if Path(name).is_absolute() else HERE/name
            if sha(dependency)!=digest:raise ValueError('Changed observer build dependency')
        for name,digest in receipt['outputs'].items():
            if sha(root/name)!=digest:raise ValueError('Changed observer build')
    verilog=ngspice/'src/xspice/verilog'
    selections={
        'next_advance_cb':(vpi,'static PLI_INT32 next_advance_cb(struct t_cb_data *cb)\n{','/* Callback function - new output value. */'),
        'start_cb':(vpi,'static PLI_INT32 start_cb(struct t_cb_data *cb)\n{','/* VPI initialisation. */'),
        'output_cb':(vpi,'static PLI_INT32 output_cb(struct t_cb_data *cb)\n{','/* Callback function - simulation is starting. */'),
        'pthread_yield':(verilog/'coroutine_cosim.h','/* On a Unix-like OS','\n#endif\n#endif'),
        'bridge_context':(verilog/'icarus_shim.h','struct ng_vvp {','/* Function to find the current'),
        'generic_event':(icarus/'vvp/schedule.cc','struct generic_event_s : public event_s {','void generic_event_s::single_step_display'),
        'sync_execution':(icarus/'vvp/vpi_callback.cc','void sync_cb::run_run()','static vvp_time64_t get_sync_cb_time')}
    pieces={name:{'path':str(path),'sourceSha256':sha(path),'excerpt':excerpt(path.read_text(),start,end)} for name,(path,start,end) in selections.items()}
    body=pieces['next_advance_cb']['excerpt'];before,after=body.split('        cr_yield_to_spice(&ctx->cr_ctx);')
    for assigned,used in [('val.format = vpiVectorVal;','vpi_put_value('),('i = ctx->ins ? 0 : ctx->outs;','ctx->ports[i]'),
                          ('vl_time = get_time(ctx);','ctx->cosim_context->vtime < vl_time'),
                          ('ticks = (uint64_t)','if (ticks > 0)')]:
        if after.index(assigned)>after.index(used):raise ValueError('Changed reviewed continuation ordering')
    if 'cb->' in after:raise ValueError('Callback parameter newly used after yield')
    start=pieces['start_cb']['excerpt']
    if start[start.index('    next_advance_cb(cb);'):].strip()!='next_advance_cb(cb);\n    return 0;\n}':
        raise ValueError('Startup caller gained continuation work')
    return {'qualified':False,'scope':'Pinned next_advance_cb suspension at pthread cr_yield_to_spice, including its direct startup caller. Manual control-flow argument, not a general stack verifier.',
        'sources':{n:sha(HERE/n) for n in ('callback_continuation_review.py','build_private_sync_identity.py','build_private_sync_bridge.py','fixtures/private_sync_bridge.h','reports/live-cosim-state/model/live_state_audit.h')},
        'buildReceipts':{str(p/'build.json'):sha(p/'build.json') for p in (identity_build,icarus)},
        'sourceExcerpts':pieces,
        'entryConditions':['One Icarus instance using the reviewed pthread coroutine backend.','Observation occurs while SPICE owns the same mutex used by the HDL condition wait.','Pinned source/build lineage remains unchanged; foreign callbacks and asynchronous writes are outside the argument.'],
        'continuationArgument':[
            'cb is read to obtain ctx before entering the loop and is not read after the yield. Its stale local value need not be copied to compare this continuation.',
            'val.format and the input-loop index i are assigned before their next use. val.value.vector is assigned on every path that passes val to vpi_put_value.',
            'vl_time is assigned by get_time before comparison or logging, and ticks is assigned before its conditional and set_stop call. Previous values of these scalar locals cannot influence the reviewed resumed path.',
            'ctx survives the yield and is subsequently dereferenced. Its identity and relevant referents therefore remain part of the state contract.',
            'The initial start_cb directly calls next_advance_cb and only returns zero afterward. Its initialization locals are not read after that call returns; this does not inventory the outer startup callback object.',
            'The pthread condition wait cannot return to user callback code until the HDL thread reacquires the shared mutex. This establishes a paused observation boundary, not restoration after HDL advancement.',
            'After the stop callback returns, sync_cb::run_run uses cur for deletion and resets observer/execution bookkeeping. generic_event_s::run_run subsequently reads delete_obj_when_done and may delete obj. These surrounding objects are live continuation state even though they are absent from pending queue topology.'],
        'remainingStateContract':[
            {'root':'ng_vvp context and ports','existingEvidence':'reports/live-cosim-state/model/live_state_audit.h serializes bridge timing, pending counts, stop flag and port values; callback headers compare user-data identity.','missing':'Integrate referent observation with the same callback boundary controls; establish port handle/back-reference identity and the live stop_cb relationship, rather than only its non-null flag.'},
            {'root':'sync_callback / sync_cb','existingEvidence':'Live callback header observer records lifetime IDs, active/canceled state, synchronization mode, time and structural back-references.','missing':'Match executing wrapper identity and continuation roots; identity-handoff board controls remain required.'},
            {'root':'executing generic event and scheduler frame','existingEvidence':'Source identifies obj and delete_obj_when_done as reads after callback return.','missing':'Observe executing event identity and deletion flag, link obj to the live callback, and account for the scheduler continuation separately from pending queues.'},
            {'root':'OS synchronization and storage lifecycle','existingEvidence':'The pinned pthread mutex defines observation ownership.','missing':'No thread-stack serialization, mutex snapshot/restore or freed-storage equivalence is established.'}],
        'conclusion':'Do not add opaque stack-byte comparisons for overwritten next_advance_cb temporaries. Preserve and test its surviving context root and surrounding callback/event state instead.',
        'notEstablished':['General rejected-trial rollback, startup/recovery qualification or all callback families.','Dynamic equivalence of unobserved referents, handle lifetimes, scheduler frames or freed storage.','A compiler-independent formal dataflow proof or correctness of the physical board model.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('vpi','identity-build','icarus','ngspice','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();result=assess(a.vpi,a.identity_build,a.icarus,a.ngspice)
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(a.out)
