#!/usr/bin/env python3
"""Fail closed when the compiled board needs unsupported thread referents."""
import argparse,json
from pathlib import Path
from thread_board_reachability import analyze
from retained_evidence import check
from audit_log import records
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
# Audited vector/scalar instruction families for the pinned compiled board.
# New families require review; do not infer safety from a substring blacklist.
BOARD_OPCODES=frozenset('%add %addi %and %assign/vec4 %assign/vec4/a/d %assign/vec4/off/d %blend %callf/vec4 %cmp/e %cmp/ne %cmp/u %cmp/z %cmpi/e %cmpi/ne %cmpi/u %concat/vec4 %concati/vec4 %dup/vec4 %end %flag_get/vec4 %flag_inv %flag_mov %flag_or %flag_set/imm %flag_set/vec4 %fork %inv %ix/load %ix/vec4 %jmp %jmp/0 %jmp/0xz %jmp/1 %join %load/vec4 %mod/s %mul/wr %nor/r %or %pad/u %parti/s %pop/vec4 %pushi/real %pushi/vec4 %replicate %ret/vec4 %store/vec4 %subi %vpi_call/w %vpi_func/r %wait %xor %xor/r'.split())
BOARD_VPI_CALLS=frozenset('$display $fflush $readmemh $realtime $strobe'.split())


def compiled_contract(text):
    program=analyze(text);unknown=set(program['opcodeCounts'])-BOARD_OPCODES
    calls={c['name'] for c in program['vpiCalls']}
    if unknown or calls-BOARD_VPI_CALLS:raise ValueError('Unaudited board opcode/VPI family: '+str(sorted(unknown | (calls-BOARD_VPI_CALLS))))
    if any(program['emitted'][key] for key in ('automaticScopes','eventControls','detach','waitFork','disableFork')):raise ValueError('Board requires additional context/event/lifecycle coverage')
    return dict(compiledProfileAccepted=True,automaticScopes=False,eventControls=False,detachedThreads=False,waitFork=False,objectProducingInstructions=False)


def validate_thread(thread):
    if any(thread[k] for k in ('writeContext','readContext','event','eventCount')):raise ValueError('Unexpected board context/event-control referent')
    if thread['objects']:raise ValueError('Unexpected board object stack')
    if thread['state'][1]=='1' or thread['state'][2]=='1' or thread['children'][1]:raise ValueError('Unexpected detached/wait-fork board state')


def validate_snapshot(snapshot):
    for thread in snapshot['threads']:validate_thread(thread)


def assess(root):
    check(root);assessment=json.loads((root/'assessment.json').read_text())
    receipt=root/'observe/run.json'
    if not assessment.get('controlsPassed') or assessment['receipts']['observe']!=sha(receipt):raise ValueError('Need reviewed normal board evidence')
    profile=compiled_contract((root/'observe/io.vvp').read_text())
    counts=dict(threads=0,stacks=0,states=0,detachedSets=0,begins=0,ends=0)
    for line in records(root/'observe/ngspice.log',('VT_THREAD ','VT_STACKS ','VT_STATE ','VT_CHILDREN ','VT_BEGIN ','VT_END ')):
        a=line.split()
        if a[0]=='VT_THREAD':
            if len(a)!=10 or any(int(v,16) if v!='(nil)' else 0 for v in a[6:9]) or int(a[9]):raise ValueError('Nonzero context/event referent')
            counts['threads']+=1
        elif a[0]=='VT_STACKS':
            if len(a)!=5 or int(a[4]):raise ValueError('Nonempty object stack')
            counts['stacks']+=1
        elif a[0]=='VT_STATE':
            if len(a)!=2 or len(a[1])!=9 or a[1][1:3]!='00':raise ValueError('Unexpected detached/wait-fork state')
            counts['states']+=1
        elif a[0]=='VT_CHILDREN' and a[1]=='1':
            if a!=['VT_CHILDREN','1','0']:raise ValueError('Unexpected detached child set')
            counts['detachedSets']+=1
        elif a[0]=='VT_BEGIN':counts['begins']+=1
        elif a[0]=='VT_END':counts['ends']+=1
    expected=assessment['observedState']['liveThreadObservations']*2
    boundaries=assessment['observedState']['boundaries']*2
    if any(counts[k]!=expected for k in ('threads','stacks','states','detachedSets')) or counts['begins']!=boundaries or counts['ends']!=boundaries:raise ValueError('Incomplete reviewed-state coverage')
    return dict(qualified=False,compiledProfile=profile,allReviewedThreadRecordsSatisfyContract=True,counts=counts,
                retainedRoot=str(root),manifestSha256=sha(root/'manifest.json'),assessmentSha256=sha(root/'assessment.json'),receiptSha256=sha(receipt),
                scope='Absence of automatic contexts, thread object-stack entries, event-control registers and detached/wait-fork state in every reviewed normal thread snapshot, guarded by an explicit compiled opcode/VPI profile.',
                notEstablished=['Mutable scope membership, net/fanout/array contents and instruction operands','Other compiled profiles or unobserved operating windows','Freed-storage equivalence or general rollback'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=assess(a.root)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2),flush=True)
