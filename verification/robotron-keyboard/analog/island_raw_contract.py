#!/usr/bin/env python3
"""Pin remaining raw island and scheduled-assignment ownership before implementation."""
import argparse,hashlib,json,re,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent

def profile(compiled):
    islands={};ports=[];branches=[]
    for line in compiled.splitlines():
        if ' .island ' in line:
            m=re.fullmatch(r'(\S+) \.island tran;',line)
            if not m or m[1] in islands:raise ValueError('Unsupported or duplicate island')
            islands[m[1]]='tran'
        elif re.match(r'\S+ \.(port|import) ',line):
            m=re.fullmatch(r'(\S+) \.(port|import) (\S+), (\S+);',line)
            if not m:raise ValueError('Malformed island port')
            ports.append(dict(label=m[1],kind=m[2],island=m[3],source=m[4]))
        elif re.match(r'\s*\.(r?tran)',line):
            m=re.fullmatch(r'\s*\.(tranif[01]) (\S+), (\S+) (\S+), (\S+);',line)
            if not m:raise ValueError('Unadmitted board transmission branch')
            branches.append(dict(kind=m[1],island=m[2],a=m[3],b=m[4],enable=m[5]))
    labels={p['label']:p for p in ports}
    if not islands or not branches or len(labels)!=len(ports):raise ValueError('Incomplete or aliased island profile')
    for p in ports:
        if p['island'] not in islands:raise ValueError('Port has foreign island')
    for b in branches:
        if b['island'] not in islands or any(k not in labels or labels[k]['island']!=b['island'] for k in (b['a'],b['b'],b['enable'])):raise ValueError('Branch has foreign port')
    return dict(islands=islands,ports=ports,branches=branches,bindingLimit='Compiled membership only; native graph/class and operational bindings remain required.')

def build(archive,board,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed archive')
    check(board);files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp_island.h','vvp_island.cc','island_tran.cc','schedule.cc'):
            members=[m for m in tar.getmembers() if m.name.endswith('/vvp/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];i=text.index(start);j=text.index(end,i+len(start))
        return dict(file=name,firstLine=text[:i].count('\n')+1,excerpt=text[i:j])
    evidence={
        'portStorage':section('vvp_island.h','class vvp_island_port  :','inline vvp_vector8_t island_get_value'),
        'inputEqualityAndPartialWrites':section('vvp_island.cc','void vvp_island_port::recv_vec4(', 'void vvp_island_port::force_flag('),
        'outputFilteringAndEquality':section('vvp_island.cc','void island_send_value(', 'vvp_island::vvp_island()'),
        'runAndTemporaryResolution':section('island_tran.cc','void vvp_island_tran::run_island()', 'void vvp_island_tran::count_drivers('),
        'outputThenScratchClear':section('island_tran.cc','void vvp_island_branch_tran::run_output()', 'void compile_island_tran('),
        'assignmentPayloadAndDispatch':section('schedule.cc','struct assign_vector8_event_s', 'struct assign_real_event_s'),
        'genericWrapper':section('schedule.cc','struct generic_event_s', 'static const size_t GENERIC_CHUNK_COUNT'),
    }
    result=dict(qualified=False,scope='Pinned source ownership and compiled membership audit. No new native raw-state coverage or operational qualification.',archiveSha256=ARCHIVE_SHA,boardManifestSha256=sha(board/'manifest.json'),compiledProfile=profile((board/'board.vvp').read_text()),sources={n:hashlib.sha256(t.encode()).hexdigest() for n,t in files.items()},evidence=evidence,
        requiredRawStorage=['vvp_island_port.invalue','vvp_island_port.outvalue','vvp_island_port.value','assign_vector8_event_s.val'],
        requirements=[
            'Preserve raw bytes and actual lengths for all three port vectors, including empty constructor/scratch storage. Keep the legacy triplet view as a cross-check, not an exact encoding.',
            'Full input writes use raw equality to suppress scheduling. Partial-first input expands the vector; later partial writes merge with existing input, unlike resolver fresh-Z replacement. Cover clipping and untouched bits.',
            'Observe synchronous output callbacks while temporary resolution vectors remain live. run_output sends before clearing scratch; idle snapshots alone cannot qualify scratch payloads.',
            'Keep island flag, mesh order, branch enable state, direction, resistance and partial-width configuration together with raw port caches. Bind each port to native graph/class and filter ownership.',
            'Generic island wrappers contain event identity/ownership, not a separate strength vector. Preserve queued/executing wrapper-to-island bindings while covering the port payload itself.',
            'Scheduled vector-8 assignments own separate raw payload vectors and tagged destinations. Cover pending and executing assignments, allocation/lifetime identity, raw collision faults and restored continuation.',
            'Require exact native family admission, early/late unsupported-family refusal, allocation growth and original-runtime continuation controls before compact/combined integration.',
            'Exercise real raw-strength inputs and 0x00/0x88 collisions in input/output/scratch and scheduled payloads. The scalar/switch helper oracle does not establish complete island dispatch coverage.',
            'Add a subsequent runtime revision without changing pinned active campaigns; preserve all preceding graph/filter/queue checks and measure actual full-scan and changing-state cost.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','board','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.board,a.out)
