#!/usr/bin/env python3
"""Inventory compiled static memories and pin their native ownership semantics."""
import argparse, hashlib, json, re, tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from compiled_scope_profile import analyze
from ttl7406_probe import sha


def profile(text):
    scopes={s['label']:s for s in analyze(text)['scopes']}
    current=None;arrays={};ports=[]
    for line in text.splitlines():
        line=line.strip()
        declaration=re.match(r'^(\S+)\s+\.scope\s',line)
        recall=re.fullmatch(r'\.scope\s+(\S+);',line)
        if declaration:current=declaration[1]
        if recall:current=recall[1]
        if not re.search(r'\s\.array(?:\s|/)',line):continue
        port=re.fullmatch(r'(\S+)\s+\.array/port\s+(\S+),\s*(\S+);',line)
        if port:
            address=port[3]
            ports.append(dict(label=port[1],array=port[2],address=int(address) if re.fullmatch(r'-?\d+',address) else address,
                              addressKind='constant' if re.fullmatch(r'-?\d+',address) else 'signal',scope=current))
            continue
        array=re.fullmatch(r'(\S+)\s+\.array\s+("(?:\\.|[^"\\])*"),\s*(-?\d+)\s+(-?\d+),\s*(-?\d+)\s+(-?\d+);',line)
        if array is None:raise ValueError('Unaudited array declaration: '+line)
        if current not in scopes or scopes[current]['automatic']:raise ValueError('Need a known static array scope')
        label,name,last,first,msb,lsb=array.groups()
        if label in arrays:raise ValueError('Duplicate array declaration')
        first,last,msb,lsb=map(int,(first,last,msb,lsb))
        arrays[label]=dict(label=label,name=json.loads(name),scope=current,compilerFirst=first,compilerLast=last,
                           msb=msb,lsb=lsb,words=abs(last-first)+1,width=abs(msb-lsb)+1,storage='static-four-state-variable')
    if not arrays or len({p['label'] for p in ports})!=len(ports):raise ValueError('Missing arrays or duplicate read ports')
    for port in ports:
        if port['array'] not in arrays or port['scope'] not in scopes or scopes[port['scope']]['automatic']:raise ValueError('Unknown array or automatic read-port context')
    return dict(arrays=list(arrays.values()),ports=ports,logicalBits=sum(a['words']*a['width'] for a in arrays.values()))


def build(archive,vvp,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/array.cc','vvp/vpi_priv.h','vvp/vvp_net.cc','vvp/vvp_net.h'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous native source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    result=dict(qualified=False,scope='Compiled static four-state memory/read-port inventory and pinned source semantics; not native state coverage.',
        compiledSha256=sha(vvp),archiveSha256=ARCHIVE_SHA,compiled=profile(vvp.read_text()),
        sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'arrayFields':section('vvp/vpi_priv.h','struct __vpiArray :','class __vpiDarrayVar'),
            'initializationAndScopeAttachment':section('vvp/array.cc','vpiHandle vpip_make_array(', 'void __vpiArray::alias_word('),
            'fourStateStorageSelection':section('vvp/array.cc','void compile_var_array(', 'void compile_var2_array('),
            'lazyWordHandleAllocation':section('vvp/array.cc','vpiHandle __vpiArray::vpi_index(', 'int __vpiArrayWord::'),
            'logicalStorageRead':section('vvp/vvp_net.cc','vvp_vector4_t vvp_vector4array_t::get_word_(', 'vvp_vector4array_aa::vvp_vector4array_aa('),
            'typedArrayRead':section('vvp/array.cc','vvp_vector4_t __vpiArray::get_word(', 'double __vpiArray::get_word_r('),
            'readPortFieldsAndConstructors':section('vvp/array.cc','class vvp_fun_arrayport  :', 'class vvp_fun_arrayport_sa'),
            'staticReadPortAddressAndPropagation':section('vvp/array.cc','void vvp_fun_arrayport_sa::recv_vec4(', 'class vvp_fun_arrayport_aa'),
            'portAttachmentAndInitialization':section('vvp/array.cc','static void array_attach_port(', 'class array_word_value_callback'),
            'wordChangeAndCallbacks':section('vvp/array.cc','void __vpiArray::word_change(', 'class array_port_resolv_list_t'),
            'compileTableIsTemporary':section('vvp/array.cc','void compile_array_cleanup(', '#ifdef CHECK_WITH_VALGRIND'),
            'aliasStorageSharing':section('vvp/array.cc','void compile_array_alias(', '/*\n * &A<label,addr>'),
        },
        requirements=[
            'Enumerate arrays through initialized scope objects; the compile-time symbol table is deleted after compilation. Bind each array and read port to its owner and validate compiled counts/ranges.',
            'Observe all logical 0/1/X/Z bits through const storage reads. Narrow cells initialize to X; wide unallocated cells represent X. Do not read padding or inactive storage unions.',
            'Do not call VPI indexing/iteration APIs that allocate vals_words while observing. Track cached word-handle presence separately; zeroing or materializing it is not observation.',
            'Include read-port list order, destination net and cached address. Invalid/X addresses become an out-of-range sentinel; read ports and callbacks can change behavior even when words agree.',
            'Account for array-level callbacks or explicitly reject nonempty unsupported lists; an empty list on the current board does not cover other profiles.',
            'Preserve shared storage identity if aliases are supported. Otherwise reject aliases, automatic arrays/ports, net arrays and other storage families before interpreting them as static four-state arrays.',
            'Inject faults in actual storage and port state while paused, restoring before execution. Use the underlying storage setter for a word fault, not __vpiArray::set_word, which propagates word changes and callbacks.',
            'Exercise unwritten X values, loaded data, partial writes, address changes, out-of-range reads, and restored word/address/link faults with unchanged continuation. Net/fanout contents and callback referents remain separate obligations.',
            'Measure board capture and review budgets before integrating complete array observations; do not omit the ROM merely because firmware bytes are separately hashed.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','vvp','out'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();build(args.archive,args.vvp,args.out)
