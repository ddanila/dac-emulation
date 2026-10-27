#!/usr/bin/env python3
"""Pin static signal storage, initialization and procedural assignment semantics."""
import argparse,hashlib,json,re,tarfile
from pathlib import Path
from compiled_scope_profile import analyze
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha


def profile(text):
    scopes={s['label']:s for s in analyze(text)['scopes']};current=None;signals={}
    for line in text.splitlines():
        line=line.strip()
        declaration=re.match(r'^(\S+)\s+\.scope\s',line)
        recall=re.fullmatch(r'\.scope\s+(\S+);',line)
        if declaration:current=declaration[1]
        if recall:current=recall[1]
        if not re.search(r'\s\.var(?:\s|/)',line):continue
        match=re.fullmatch(r'(\S+)\s+(\.var(?:/i)?)\s+("(?:\\.|[^"\\])*"),\s*(-?\d+)\s+(-?\d+);',line)
        if match is None:raise ValueError('Unaudited variable declaration: '+line)
        label,kind,name,msb,lsb=match.groups()
        if label in signals:raise ValueError('Duplicate variable label')
        if current not in scopes or scopes[current]['automatic']:raise ValueError('Need known static signal scope')
        msb,lsb=int(msb),int(lsb)
        signals[label]=dict(label=label,name=json.loads(name),scope=current,kind=kind,msb=msb,lsb=lsb,width=abs(msb-lsb)+1)
    if not signals:raise ValueError('No static signal variables')
    return dict(signals=list(signals.values()),logicalBits=sum(s['width'] for s in signals.values()))


def build(archive,vvp,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/vvp_net_sig.h','vvp/vvp_net_sig.cc','vvp/vvp_net.cc','vvp/words.cc','vvp/vthread.cc'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    result=dict(qualified=False,scope='Pinned source and compiled static-variable admission; not native payload coverage.',archiveSha256=ARCHIVE_SHA,compiledSha256=sha(vvp),compiled=profile(vvp.read_text()),
        sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'baseFields':section('vvp/vvp_net_sig.h','class vvp_fun_signal_base :','/*\n * Variables and wires'),
            'staticFields':section('vvp/vvp_net_sig.h','class vvp_fun_signal4_sa :','/*\n * Automatically allocated'),
            'constructors':section('vvp/vvp_net_sig.cc','vvp_fun_signal_base::vvp_fun_signal_base()','/*\n * Nets simply reflect'),
            'emptyMaskInitialization':section('vvp/vvp_net.cc','vvp_vector2_t::vvp_vector2_t()','vvp_vector2_t::vvp_vector2_t(unsigned long'),
            'fullAndPartialWrites':section('vvp/vvp_net_sig.cc','void vvp_fun_signal4_sa::recv_vec4(', 'void automatic_signal_base::release('),
            'unfilteredReadAndAutomaticContext':section('vvp/vvp_net_sig.cc','const vvp_vector4_t& vvp_fun_signal4_sa::vec4_unfiltered_value()', 'void vvp_fun_signal4_aa::alloc_instance('),
            'separateFunctorAndFilterInitialization':section('vvp/words.cc','void compile_variable(', 'vvp_net_t* create_constant_node('),
            'proceduralAssignmentLink':section('vvp/vthread.cc','bool of_CASSIGN_LINK(', 'bool of_CASSIGN_VEC4('),
            'deassignmentAndUnlink':section('vvp/vthread.cc','bool of_DEASSIGN(', 'bool of_DEBUG_THR('),
        },requirements=[
            'Enumerate allocated signal functors independently of visible VPI handles. Bind each signal to its registered graph node and functor pointer; compare compiled variable widths and scope admission without substituting counts for identity.',
            'Observe unfiltered bits4_ separately from wire-filter output. Force/release can make them differ; VPI-visible equality cannot prove underlying signal storage equality.',
            'Read logical vector bits only. Static bits4_ is initialized by its constructor; needs_init_, continuous_assign_active_ and cassign_link initialize explicitly, and assign_mask_ starts empty. Do not serialize padding or inactive vector allocation bytes.',
            'Preserve assign-mask width and every mask bit, including partially assigned variables. Preserve the initialized continuous-assignment flag even though vec4 receive paths use the mask; do not borrow real-signal semantics.',
            'Bind non-null cassign_link to an allocated source node and the corresponding destination port-1 graph link. Procedural assignment links differ from force-helper links and must not be conflated.',
            'Static compilation creates separate signal and wire-filter objects and schedules initial propagation. Do not assume their initial contents are interchangeable, particularly for two-state profiles; re-audit profiles outside admitted .var/.var/i static variables.',
            'Automatic, real, string, dynamic-array and object signal families require separate storage/context admission; reject unsupported signal subclasses before reading static fields.',
            'Exercise unwritten X, 0/1/X/Z, wide vectors, full/partial writes, procedural assign/deassign, assignment-source relinking and force/release. Inject actual initialized value/mask/link/flag faults, restore without propagation setters, and require unchanged continuation.',
            'Preserve native controls for paths absent from compiled board instructions. Measure full-board capture/review cost and reconstruct every normal and corrupted snapshot before integrating compact payload observations.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','vvp','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.vvp,a.out)
