#!/usr/bin/env python3
"""Pin net allocation/link semantics and inventory the compiled board profile."""
import argparse,collections,hashlib,json,re,tarfile
from pathlib import Path
from compiled_scope_profile import analyze
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha

NETWORK={'.net','.net/2u','.net8','.functor','.part','.cmp/eeq','.var','.concat8','.reduce/nor','.array/port','.resolv','.concat','.var/i','.arith/sum','.cmp/nee','.arith/sub','.cmp/eq'}
STRUCTURAL={'.scope','.param/l','.event','.event/or','.port','.array','.island','.import'}
FUNCTORS={'BUFT','MUXZ','BUFZ','AND','OR','NOT','XOR'}


def profile(text):
    program=analyze(text)
    if program['emitted']['automaticScopes']:raise ValueError('Automatic graph needs a separate ownership audit')
    counts=collections.Counter();functors=collections.Counter();labels=set()
    for line in text.splitlines():
        match=re.match(r'^(\S+)\s+(\.\S+)\s+(.*)$',line)
        if not match:continue
        label,kind,body=match.groups()
        if kind not in NETWORK|STRUCTURAL:raise ValueError('Unaudited graph declaration: '+kind)
        if label in labels:raise ValueError('Duplicate compiled label')
        labels.add(label);counts[kind]+=1
        if kind=='.functor':
            family=body.split()[0]
            if family not in FUNCTORS:raise ValueError('Unaudited functor family: '+family)
            functors[family]+=1
        if kind=='.resolv' and not body.startswith('tri,'):raise ValueError('Unaudited resolver family')
        if kind=='.island' and body!='tran;':raise ValueError('Unaudited island family')
    if not counts['.functor'] or not counts['.net']:raise ValueError('Missing compiled network')
    return dict(declarations=dict(sorted(counts.items())),functorFamilies=dict(sorted(functors.items())),
        networkDeclarationCount=sum(counts[k] for k in NETWORK),
        declarationCountsAreNotNativeAllocationCounts=True,
        reasons=['Net handles may share existing driver nodes.','Wide-input cores allocate intermediate nodes without labels.','Pool construction includes unused capacity; register handed-out allocations, not constructor calls.'])


def build(archive,vvp,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/vvp_net.cc','vvp/vvp_net.h','vvp/compile.cc','vvp/words.cc'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous native source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    result=dict(qualified=False,scope='Compiled declaration admission and pinned allocation/fanout semantics; not native graph-state coverage.',archiveSha256=ARCHIVE_SHA,compiledSha256=sha(vvp),compiled=profile(vvp.read_text()),
        sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'taggedLinkInitialization':section('vvp/vvp_net.h','template <class T> class vvp_sub_pointer_t {','typedef vvp_sub_pointer_t<vvp_net_t>'),
            'nodeFields':section('vvp/vvp_net.h','class vvp_net_t {','/*\n * Instances of this class'),
            'poolHandout':section('vvp/vvp_net.cc','static const size_t VVP_NET_CHUNK','\n#ifdef CHECK_WITH_VALGRIND\nstatic map'),
            'constructorAndLinkChanges':section('vvp/vvp_net.cc','vvp_net_t::vvp_net_t()','void vvp_net_t::count_drivers('),
            'sendTraversesDestinationPorts':section('vvp/vvp_net.h','inline void vvp_send_vec4(','extern void vvp_send_vec8('),
            'constantInputsAndUnlabelledNodes':section('vvp/compile.cc','void input_connect(','template <class T_> void make_arith('),
            'temporarySymbolTable':section('vvp/compile.cc','void compile_cleanup(void)','      delete_udp_symbols();'),
            'netHandlesShareDrivers':section('vvp/words.cc','static void do_compile_net(','void compile_netw('),
            'dynamicForceLinks':section('vvp/vvp_net.cc','void vvp_net_fil_t::force_link(','/* *** BIT operations *** */'),
        },requirements=[
            'Register every handed-out native net allocation with stable identity; exclude unallocated pool capacity and include unlabelled intermediate nodes. The compile-time symbol table is removed before execution.',
            'Serialize initialized functor/filter bindings, output head and all four tagged port links. Port links initialize through vvp_sub_pointer_t, and functor/filter pointers initialize to null. Do not read arbitrary pointed-to payloads.',
            'Validate target allocation identity before dereferencing; preserve destination input numbers and exact fanout order. Ordinary fanout traversal uses destination ports as next links; force-link helper port 2 instead stores a source back-reference. Preserve typed uses rather than treating all ports as graph edges.',
            'Record every node independently of graph traversal so removed heads/links remain detectable. Detect foreign targets and cycles without walking corrupted storage.',
            'Net declaration counts and constructor calls cannot prove allocation coverage. Cross-check handed-out allocations independently and bind queued event, code operand and array destination references to registered nodes.',
            'Exercise actual head, interior link, input-number and functor/filter-binding mutations; restore before resuming. Include unconnected nodes, multi-destination outputs, constant inputs and force-link insertion/removal.',
            'Logical graph/binding coverage is separate from functor/filter payload contents, callback contents, freed storage and rollback. Audit reachable payload families after graph coverage; do not infer coverage from shared net identity.',
            'Measure complete graph snapshot and review costs before board integration; compact representations must reconstruct complete normal and corrupted images exactly.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','vvp','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.vvp,a.out)
