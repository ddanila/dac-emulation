#!/usr/bin/env python3
"""Pin resolver cache ownership and independently inspect compiled population."""
import argparse,collections,hashlib,json,re,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from retained_evidence import check
from ttl7406_probe import sha
KINDS={'tri':'resolv_tri','tri0':'resolv_tri','tri1':'resolv_tri','triand':'resolv_triand','trior':'resolv_trior'}

def layout(nports):
    if not isinstance(nports,int) or isinstance(nports,bool) or nports<1:raise ValueError('Need positive resolver port count')
    levels=[dict(base=0,count=nports)];total=nports;span=nports
    while span>1:
        span=(span+3)//4;levels.append(dict(base=total,count=span));total+=span
    return dict(ports=nports,levels=levels,slots=total,outputIndex=total-1,extensionBases=list(range(4,nports,4)))

def profile(compiled,classes):
    if not classes or any(not isinstance(v,int) or isinstance(v,bool) or v<1 for v in classes.values()):raise ValueError('Invalid class inventory')
    rows=[];labels=set();expected=collections.Counter()
    for line in compiled.splitlines():
        if not re.match(r'\S+ \.resolv',line):continue
        m=re.fullmatch(r'(\S+) \.resolv (\w+), (.+);',line)
        if not m or m[2] not in KINDS:raise ValueError('Unaudited compiled resolver')
        if m[1] in labels:raise ValueError('Duplicate resolver label')
        labels.add(m[1]);inputs=m[3].split(', ')
        if any(not re.fullmatch(r'\S+',v) for v in inputs):raise ValueError('Malformed resolver inputs')
        tree=layout(len(inputs));expected[KINDS[m[2]]]+=1
        if tree['extensionBases']:expected['resolv_extend']+=len(tree['extensionBases'])
        rows.append(dict(label=m[1],kind=m[2],inputs=inputs,layout=tree))
    native={k:v for k,v in classes.items() if k.startswith('resolv_')}
    if not rows or dict(expected)!=native:raise ValueError('Compiled/native resolver population differs')
    return dict(resolvers=rows,nativeClasses=native,totalCacheSlots=sum(r['layout']['slots'] for r in rows),
                bindingLimit='Compiled family/port counts are aggregate evidence, not named native-object bindings.')

def build(archive,board,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    check(board);a=json.loads((board/'assessment.json').read_text())
    if not a.get('nativeClassBindingsMatchGraph'):raise ValueError('Need bound native classes')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/resolv.h','vvp/resolv.cc','vvp/compile.cc','vvp/vvp_net.h'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];i=text.index(start);j=text.index(end,i+len(start))
        return dict(file=name,firstLine=text[:i].count('\n')+1,excerpt=text[i:j])
    result=dict(qualified=False,scope='Pinned source ownership and compiled resolver population. No native payload, fault, continuation or operational qualification.',archiveSha256=ARCHIVE_SHA,boardManifestSha256=sha(board/'manifest.json'),
        compiledProfile=profile((board/'board.vvp').read_text(),a['nativeClasses']['fun']),sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'coreAndExtensionFields':section('vvp/resolv.h','class resolv_core :','/*\n * This functor type resolves'),
            'triAndWiredFields':section('vvp/resolv.h','class resolv_tri :','#endif'),
            'partialExpansionAndExtensions':section('vvp/resolv.cc','resolv_core::resolv_core(', 'resolv_tri::resolv_tri('),
            'triTreeAllocationAndDispatch':section('vvp/resolv.cc','resolv_tri::resolv_tri(', 'resolv_wired_logic::resolv_wired_logic('),
            'wiredTreeAllocationAndDispatch':section('vvp/resolv.cc','resolv_wired_logic::resolv_wired_logic(', 'resolv_triand::resolv_triand('),
            'compilerAndPullValues':section('vvp/compile.cc','void compile_resolver(', 'void compile_udp_def('),
            'vectorConstructor':section('vvp/vvp_net.h','inline vvp_vector8_t::vvp_vector8_t(unsigned', 'inline vvp_vector8_t::~vvp_vector8_t()'),
        },requirements=[
            'Observe core nports_, output net_, cache-array allocation identity and every allocated input, intermediate branch and output vector with its actual size. Constructor vectors are initialized empty; do not infer their later widths.',
            'Record allocation bounds independently of mutable nports_. A restored nports_ fault must not make observation walk beyond the original val_ allocation. Do not omit non-leaf cache slots as recomputable: native equality can stop propagation at an unchanged branch.',
            'For exact resolv_tri preserve raw bytes in every cache vector and hiz_value_. Native eeq distinguishes strength encodings with equal logical/triplet views. The puller is blended into the stored root before output; tri0/tri1 use strength 5 while recv_vec4 converts inputs with strength 6.',
            'For resolv_extend bind core_ to an admitted allocated core and preserve port_base_. Cover routing beyond port 3 and quaternary-tree boundaries even when absent from the compiled board.',
            'Partial input receives construct a fresh full-width Z vector. They do not merge untouched bits with the old leaf. Exercise clipping, partial-first initialization, empty/wide vectors, repeated writes and hidden raw-byte changes.',
            'Admit exact audited classes. Refuse other resolv_core families, resolv_extend subclasses and any unaudited wired-logic family before partial output; names alone are not native admission.',
            'Capture synchronous downstream callback observations after root update, along with leaf/intermediate caches, pull state and output destination. No private queued resolver event is declared by these classes; downstream scheduler state remains separately required.',
            'Use independent expected resolution and original-runtime continuation controls. Restore faults in leaf/branch/root vectors, puller, port count, output link and extension link/base without invoking propagation setters.',
            'Require native allocation-growth and unsupported-family controls, graph/class bindings, exact compact reconstruction and measured combined cost before board qualification. Deletion and freed-storage equivalence remain separate.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','board','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.board,a.out)
