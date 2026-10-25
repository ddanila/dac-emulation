#!/usr/bin/env python3
"""Retain a scoped source argument for the input-barrier early-return path.

This is a manually reviewed control-flow argument with freshness checks, not a
formal verifier or a claim about all callbacks and rejected analog trials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
HERE=Path(__file__).resolve().parent
TARGET=HERE/'reports/barrier-state-source/assessment.json'
ARCHIVE='894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f'


def sha(data):return hashlib.sha256(data).hexdigest()


def build(archive):
    if sha(archive.read_bytes())!=ARCHIVE:raise ValueError('Unexpected ngspice archive')
    sources={}
    selections={
        'src/xspice/verilog/coroutine_shim.h':('static void cr_yield_to_sim(struct cr_ctx *ctx) {','static void cr_safety(void) {'),
        'src/xspice/verilog/coroutine_cosim.h':('/* On a Unix-like OS','\n#endif\n#endif'),
        'src/xspice/verilog/icarus_shim.c':('static void step(struct co_info *pinfo)','static void cleanup(struct co_info *pinfo)'),
        'src/xspice/cm/cm.c':('int cm_analog_set_temp_bkpt(','/*\ncm_analog_set_perm_bkpt()')}
    with tarfile.open(archive) as package:
        for name,(start,end) in selections.items():
            data=package.extractfile('ngspice-47/'+name).read();text=data.decode()
            # coroutine_shim has a separate Windows implementation first.
            offset=text.index('#else // Pthreads') if name.endswith('coroutine_shim.h') else 0
            a=text.index(start,offset);b=text.index(end,a)
            sources[name]={'sha256':sha(data),'firstLine':text[:a].count('\n')+1,'excerpt':text[a:b].rstrip()}
    files=['fixtures/ngspice-47/d_cosim.mod','engine-patches/cosim-input-barrier.patch','engine-patches/ngspice-47-strict-time-diagnostic.patch',
           'reports/live-cosim-state/model/cfunc.mod','reports/live-cosim-state/model/live_state_audit.h',
           'reports/live-cosim-state/assessment.json']
    scheduler=(HERE/files[0]).read_text()
    sources[files[0]]={'sha256':sha(scheduler.encode()),'locators':['run: input queue processing','advance: client step and output handling','accept_output/output: output buffer writes']}
    return {'schema':1,'kind':'Manually reviewed source argument; freshness checks are not a formal proof',
            'archiveSha256':ARCHIVE,'sourceExcerpts':sources,'repositorySources':{n:sha((HERE/n).read_bytes()) for n in files},
            'pthreadContract':{'url':'https://pubs.opengroup.org/onlinepubs/7908799/xsh/pthread_cond_wait.html',
                               'requirement':'A successful condition wait returns owning the associated mutex; spurious wakeups still require reacquiring it.'},
            'entryConditions':['Initialized single-Icarus pthread bridge; SPICE owns the coroutine mutex.',
                               'A queued input lies strictly after the accepted boundary and before the trial time.',
                               'The temporary-breakpoint request succeeds, taking the input-barrier return.',
                               'No fault injection, extra VPI writer, cancellation or external worker mutates simulator state.'],
            'reviewedPath':'Uninstrumented input-barrier patch on the pinned scheduler. Observer helper calls are additional empirical evidence, not part of this no-call argument.',
            'argument':[
                'The uninstrumented barrier loop calls only cm_analog_set_temp_bkpt before returning. It precedes queued-input delivery and advance().',
                'The breakpoint helper reads circuit times and may write the breakpoint or error-message fields; it neither calls Icarus nor releases the coroutine mutex.',
                'advance() resumes Icarus through info.step; the pthread bridge releases SPICE ownership only while waiting in cr_yield_to_sim. Neither is reached on the successful barrier branch.',
                'Icarus cannot leave its condition wait while SPICE retains the same mutex, including after a spurious wakeup. Pending HDL events therefore cannot execute through this branch.',
                'The branch makes no writes to the pending-output buffer and does not call output(), accept_output() or cm_event_get_ptr. Local buffer contents cannot change through this branch under the entry conditions.'],
            'conclusion':'Private event-queue traversal is not necessary to justify non-execution on this specific successful early-return branch. This does not prove rollback after advancing the HDL.',
            'notEstablished':['Immutability of the entire surrounding callback or trial; queued input and XSPICE history can change outside the reviewed branch.',
                              'State preservation on failed-breakpoint, advance, output, startup or cleanup paths.',
                              'Complete HDL event-queue serialization or general rollback, Windows fiber behavior, or all physical/firmware scenarios.',
                              'Source-to-binary equivalence beyond the retained build lineage; changed sources or bridge backends require a new review.'],
            'qualified':False}


def check():
    result=json.loads(TARGET.read_text())
    for name,digest in result['repositorySources'].items():
        if sha((HERE/name).read_bytes())!=digest:raise ValueError('Changed source argument dependency: '+name)
    if result['archiveSha256']!=ARCHIVE:raise ValueError('Changed archive identity')
    if result['qualified'] is not False:raise ValueError('Source argument cannot qualify whole-board rollback')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path);p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.check:check()
    else:
        if not a.archive:p.error('Need --archive')
        TARGET.parent.mkdir(parents=True,exist_ok=True);TARGET.write_text(json.dumps(build(a.archive),indent=2)+'\n')
    print(TARGET)
