#!/usr/bin/env python3
"""Extract native port/bit ownership, initialization and consumer requirements."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def assess(archive):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed native archive')
    paths=('vvp/vpi_priv.h','vvp/vpi_scope.cc','vvp/compile.cc','vvp/vpi_priv.cc');sources={}
    with tarfile.open(archive) as tar:
        for path in paths:
            found=[m for m in tar.getmembers() if m.name.endswith('/'+path)]
            if len(found)!=1:raise ValueError('Missing native source')
            sources[path]=tar.extractfile(found[0]).read().decode()
    def section(path,start,end):
        text=sources[path];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=path,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    evidence=dict(fields=section('vvp/vpi_priv.h','class vpiPortInfo  :','/*\n * This is used by system calls'),
        constructorsConsumersAndAttachments=section('vvp/vpi_scope.cc','vpiPortInfo::vpiPortInfo(', 'void compile_port_info('),
        portCompilation=section('vvp/vpi_scope.cc','void compile_port_info(', '\n}',),
        deferredNetResolution=section('vvp/compile.cc','struct functor_gen_resolv_list_s:', '/*\n *  vpiHandle lookup'),
        intermoduleConsumer=section('vvp/vpi_priv.cc','      vvp_net_t* net1 = port1->get_port();','      if (!dynamic_cast<vvp_fun_buft*>'))
    # Include the compilation function's closing brace in the evidence.
    evidence['portCompilation']['excerpt']+='\n}'
    return dict(qualified=False,completed=True,archiveSha256=ARCHIVE_SHA,
        nativeSources={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()},evidence=evidence,
        findings=['Ports carry parent scope, index, direction, width, owned name, optional resolved net reference and an ordered port-bit vector.',
            'Port bits carry parent-port and bit-index fields and are separately attached to scope intern lists.',
            'Native bit iteration allocates from port width but fills from the vector length; malformed size must be refused before invoking this consumer.',
            'With a buffer label, the port constructor submits a possibly deferred net lookup without first assigning ref_. Attachment alone therefore does not prove this field initialized.',
            'Intermodule-path consumers dereference resolved net references. Scope object IDs/types do not capture these port payloads.'],
        requirements=['Register exact port and bit allocation families and owned name bounds at native construction/handoff; reject unknown pointers before casts.',
            'Require completed reference resolution before reading port net storage, or track its initialized state explicitly; bind nonnull references to admitted net identities.',
            'Capture parent/index/direction/width/name bytes, net reference, ordered bit identities and each bit parent/index. Validate membership before bit dereference and refuse unsupported subclasses.',
            'Keep bridge port structures, admitted signal handles and native VPI port metadata distinct; bind them where their compiled relationships justify it.',
            'Preserve restored port-bit ordering and foreign-pointer counterexamples, zero-output refusal, original continuation and operational cost controls.',
            'Audit runtime modules before relying on initialization-only fields; these selected source excerpts are not a whole-program nonmutation proof.'],
        scope='Pinned source contract for native port metadata payload coverage. No new payload observer or lifetime/operational qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args();r=assess(a.archive)
    if a.check:
        if r!=json.loads(a.out.read_text()):raise ValueError('Changed port source contract')
    else:a.out.write_text(json.dumps(r,indent=2)+'\n')
