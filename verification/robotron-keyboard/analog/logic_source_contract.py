#!/usr/bin/env python3
"""Pin logic cache ownership and distinguish stateless forwarding functors."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from retained_evidence import check
from ttl7406_probe import sha

STATELESS={'vvp_fun_bufz','vvp_fun_buft'}
CACHED={'vvp_fun_muxz','vvp_fun_and','vvp_fun_or','vvp_fun_xor','vvp_fun_not','vvp_fun_buf'}


def classify(classes):
    if not classes or any(not isinstance(n,int) or isinstance(n,bool) or n<=0 for n in classes.values()):raise ValueError('Invalid native class inventory')
    return dict(statelessForwarders={k:v for k,v in classes.items() if k in STATELESS},
                cachedLogic={k:v for k,v in classes.items() if k in CACHED},
                otherFamilies={k:v for k,v in classes.items() if k not in STATELESS|CACHED})


def build(archive,board,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    check(board);assessment=json.loads((board/'assessment.json').read_text())
    if not assessment.get('nativeClassBindingsMatchGraph'):raise ValueError('Need bound native class evidence')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/logic.h','vvp/logic.cc','vvp/vvp_net.h','vvp/schedule.h','vvp/schedule.cc'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end=None):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start)) if end else len(text)
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    result=dict(qualified=False,scope='Pinned logic ownership semantics and initial native class admission; no new runtime payload or queue coverage.',archiveSha256=ARCHIVE_SHA,boardManifestSha256=sha(board/'manifest.json'),
        observed=classify(assessment['nativeClasses']['fun']),sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'functorBaseHasNoInstanceFields':section('vvp/vvp_net.h','class vvp_net_fun_t {','/*\n * A vvp_net_fil_t'),
            'booleanCacheFields':section('vvp/logic.h','class vvp_fun_boolean_ :','class vvp_fun_equiv'),
            'unaryCacheFields':section('vvp/logic.h','class vvp_fun_buf_not_ :','/*\n * The vvp_fun_bufz'),
            'forwarderAndMuxFields':section('vvp/logic.h','class vvp_fun_bufz:', 'class vvp_fun_muxr'),
            'inversionFields':section('vvp/logic.h','class vvp_fun_not:', '#endif'),
            'booleanInitializationAndScheduling':section('vvp/logic.cc','vvp_fun_boolean_::vvp_fun_boolean_(', 'vvp_fun_and::vvp_fun_and('),
            'unaryInitializationAndScheduling':section('vvp/logic.cc','vvp_fun_buf_not_::vvp_fun_buf_not_(', 'vvp_fun_buf::vvp_fun_buf('),
            'forwardersDoNotRetainOperands':section('vvp/logic.cc','vvp_fun_bufz::vvp_fun_bufz()', 'vvp_fun_muxr::vvp_fun_muxr()'),
            'muxInitializationCacheAndDispatch':section('vvp/logic.cc','vvp_fun_muxz::vvp_fun_muxz(', 'vvp_fun_not::vvp_fun_not('),
            'andDispatch':section('vvp/logic.cc','vvp_fun_and::vvp_fun_and(', 'vvp_fun_equiv::vvp_fun_equiv('),
            'orXorDispatch':section('vvp/logic.cc','vvp_fun_or::vvp_fun_or('),
            'genericEventInterface':section('vvp/schedule.h','struct vvp_gen_event_s\n{', '/*\n * This runs the simulator.'),
            'genericWrapperOwnership':section('vvp/schedule.cc','struct generic_event_s :', 'static const size_t GENERIC_CHUNK_COUNT'),
            'queuedFunctorScheduling':section('vvp/schedule.cc','void schedule_functor(', 'void schedule_at_start_of_simtime('),
        },requirements=[
            'BUFZ/BUFT and their common vvp_net_fun_t base have no mutable per-instance data fields beyond runtime type/binding. Preserve exact native-class and graph bindings; do not invent operand caches for those forwarding classes. This does not remove downstream filter, fanout, callback or allocator obligations.',
            'Mux caches a_, b_, select_ and has_run_ initialize to Z/Z, SEL_BOTH and false. Observe all cached inputs, including the currently unselected one: its update can be non-propagating and still change a later selected output.',
            'Boolean gates retain four initialized input vectors and a nullable pending destination. Unary BUF/NOT retain one input vector and that destination. AND/OR/XOR also retain the initialized inversion flag; do not infer inversion solely from class identity.',
            'Observe cached inputs while idle as well as queued. The stored net_ is a pending dispatch destination, not permanent ownership: receive schedules only when it is null, and run_run clears it before sending output.',
            'Bind allocated graph functor identity to the properly cast vvp_gen_event_s identity and its actual scheduler wrapper. Multiple inheritance may adjust pointers; do not reinterpret one pointer as the other. Include queued and executing wrappers and scheduling region/order.',
            'Preserve independent allocation identities and initialized fields. Generic-event base has no payload fields, but scheduler wrappers separately own target, deletion flag and queue links; a net_ value alone cannot prove wrapper coverage.',
            'Read logical 0/1/X/Z bits only. Cover partial vector receives and wide vectors; do not serialize padding, temporary run_run output vectors or uninitialized storage.',
            'Native controls must exercise unselected-input changes followed by selection, X/Z selection blending, partial and repeated inputs, inverted gates, and queued/idle transitions. Restore cache/select/run-flag/destination/inversion faults before execution without propagation setters.',
            'Preserve existing NOT controls while extending all-node coverage; queued NOT coverage does not establish idle NOT or other logic family coverage. Unknown subclasses and real mux storage require separate admission.',
            'Measure board output/runtime and retain exact full-versus-compact reconstruction before integration. This source audit does not establish native observation, fault detection, continuation or general rollback.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','board','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.board,a.out)
