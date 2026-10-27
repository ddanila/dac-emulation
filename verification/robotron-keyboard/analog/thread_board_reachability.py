#!/usr/bin/env python3
"""Inventory compiled lifecycle instructions with pinned native ownership evidence."""
import argparse,collections,json,re,tarfile
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ARCHIVE_SHA='c3a18398dd25073845550af2f35926193f4d3aa7cd7080122bdc501f59717c00'


def analyze(text):
    instructions=[];scopes=[];calls=[]
    quoted=r'"(?:\\.|[^"\\])*"'
    scope_pattern=re.compile(r'(\S+)\s+\.scope\s+([^,]+),\s*'+quoted+r'\s+'+quoted+r'\s+\d+\s+\d+(?:,\s*\d+\s+\d+\s+(\d+),\s*\S+)?;')
    for number,line in enumerate(text.splitlines(),1):
        stripped=line.strip()
        # VVP permits an instruction on the same line as its defining label.
        match=re.match(r'^(?:[^\s%"]+\s+)?(%[A-Za-z0-9_./]+)(?=[\s;])',stripped)
        if match:
            opcode=match[1];instructions.append(dict(line=number,opcode=opcode,text=line))
            if opcode.startswith('%vpi_'):
                task=re.search(quoted,stripped[match.end():])
                if task is None:raise ValueError('Unrecognized VPI instruction')
                calls.append(dict(line=number,opcode=opcode,name=json.loads(task[0]),text=line))
        if re.match(r'^\S+\s+\.scope\s',stripped):
            m=scope_pattern.fullmatch(stripped)
            if m is None:raise ValueError('Unrecognized scope declaration')
            automatic=int(m[3] or 0)
            if automatic not in (0,1):raise ValueError('Invalid automatic scope flag')
            scopes.append(dict(line=number,label=m[1],kind=m[2],automatic=bool(automatic)))
    if not instructions or not scopes:raise ValueError('Missing compiled instructions/scopes')
    counts=dict(sorted(collections.Counter(i['opcode'] for i in instructions).items()))
    relevant=[i for i in instructions if any(x in i['opcode'] for x in ('fork','join','disable','callf','exec_ufunc','evctl'))]
    return dict(opcodeCounts=counts,lifecycleInstructions=relevant,scopes=scopes,vpiCalls=calls,
                emitted=dict(detach=bool(counts.get('%join/detach')),waitFork=bool(counts.get('%wait/fork')),disableFork=bool(counts.get('%disable/fork')),automaticScopes=any(s['automatic'] for s in scopes),eventControls=any(k.startswith('%evctl') for k in counts),strobe=any(c['name'] in ('$strobe','$strobeh','$strobeb','$strobeo','$fstrobe','$fstrobeh','$fstrobeb','$fstrobeo') for c in calls)))


def build(vvp,archive,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned Icarus archive')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/vthread.cc','vvp/schedule.cc','vpi/sys_display.c','vvp/vpi_callback.cc'):
            matches=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(matches)!=1:raise ValueError('Ambiguous native source')
            files[name]=tar.extractfile(matches[0]).read().decode()
    def excerpt(name,start,end):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    import hashlib
    result=dict(qualified=False,scope='Compiled-board lifecycle reachability inventory and pinned native semantics. Absence of opcodes is scoped to this compiled input; it does not establish whole-runtime rollback or dynamic execution coverage.',compiled=dict(path=str(vvp),sha256=sha(vvp),**analyze(vvp.read_text())),sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},evidence={
        'synchronousCallbackRegistration':excerpt('vvp/vpi_callback.cc','make_sync(p_cb_data', 'static struct __vpiCallback* make_afterdelay('),
        'runningThreadFlag':excerpt('vvp/vthread.cc','void vthread_delay_delete()', '/*\n * This function runs each thread'),
        'detach':excerpt('vvp/vthread.cc','bool of_JOIN_DETACH(', '/*\n * %load/ar'),
        'waitFork':excerpt('vvp/vthread.cc','bool of_WAIT_FORK(', '/*\n * %xnor'),
        'synchronousCallbackMarksDelay':excerpt('vvp/schedule.cc','void schedule_generic(', 'static bool sim_started;'),
        'strobeSchedulesSynchronousCallback':excerpt('vpi/sys_display.c','static PLI_INT32 sys_strobe_calltf(', '/*\n * The monitor_info array')},
        requirements=['Keep native detached/wait-fork/cancellation controls as simulator evidence; do not invent a keyboard stimulus to execute instructions absent from the pinned compiled board.',
                      'A strobe call makes the delayed-delete flag reachable through synchronous callback scheduling. Whether its thread ends and enters the deletion queue requires execution or control-flow evidence; opcode absence alone cannot exclude deferred deletion.',
                      'Validate current compiled input before transferring any absence claim. Labelled instructions, VPI calls and automatic scopes must be included.',
                      'Native fixture storage reuse with fresh identities does not establish freed-storage contents or general rollback.'])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('vvp','archive','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.vvp,a.archive,a.out)
