#!/usr/bin/env python3
"""Extract native scope metadata initialization and consumers from pinned sources."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def assess(archive):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned Icarus archive')
    paths=('vvp/vpi_priv.h','vvp/vpi_scope.cc','vvp/vpi_time.cc','vvp/vpi_priv.cc','vvp/words.cc','vvp/compile.cc','vvp/array.cc','vvp/event.cc','vvp/enum_type.cc')
    source={}
    with tarfile.open(archive) as tar:
        for path in paths:
            matches=[m for m in tar.getmembers() if m.name.endswith('/'+path)]
            if len(matches)!=1:raise ValueError('Missing/ambiguous source')
            source[path]=tar.extractfile(matches[0]).read().decode()
    def section(path,start,end):
        text=source[path];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=path,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    evidence={
        'scopeFields':section('vvp/vpi_priv.h','class __vpiScope :','extern __vpiScope* vpip_peek_current_scope'),
        'metadataReadsAndConstructor':section('vvp/vpi_scope.cc','__vpiScope::__vpiScope(','class vpiScopeModule'),
        'declarationAndTimescale':section('vvp/vpi_scope.cc','void\ncompile_scope_decl(','void vpip_attach_to_current_scope('),
        'objectAttachment':section('vvp/vpi_scope.cc','void vpip_attach_to_scope(','/*\n * When the compiler encounters'),
        'scopeIterator':section('vvp/vpi_scope.cc','static vpiHandle module_iter(','__vpiScope::__vpiScope('),
        'timeConversion':section('vvp/vpi_time.cc','void vpip_time_to_timestruct(','static void timevar_get_value('),
    }
    # Retain call-site context without claiming that textual matches prove
    # a whole-program absence of runtime writes or alias-based mutation.
    calls=[]
    for path,text in source.items():
        if not path.endswith('.cc'):continue
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if 'vpip_attach_to_scope(' in line or 'vpip_attach_to_current_scope(' in line:
                calls.append(dict(file=path,line=i+1,context='\n'.join(lines[max(0,i-3):i+4])))
    patch=HERE/'engine-patches/icarus-scope-observer.patch'
    return dict(completed=True,qualified=False,archiveSha256=ARCHIVE_SHA,
        nativeSources={p:hashlib.sha256(s.encode()).hexdigest() for p,s in source.items()},
        sources={n:sha(HERE/n) for n in ('scope_metadata_contract.py','scope_referents.py','engine-patches/icarus-scope-observer.patch','thread_board_reachability.py','ttl7406_probe.py')},
        counterexampleAssessmentSha256=sha(HERE/'reports/scope-referents/assessment.json'),
        evidence=evidence,attachmentCallSites=calls,
        existingWalkerPatch=patch.read_text(),
        findings=['Scope declaration initializes file/line fields, parent, context roots and inherited time scale; compile_timescale overrides the scale.',
                  'Scope intern attachment uses push_back; the inspected call sites construct declarations, ports, nets, arrays, events and enum types.',
                  'VPI metadata and scaled-time consumers read these fields after initialization. Function subtype also carries type, width and initial-value fields.',
                  'Current static-scope traversal dynamically casts every intern pointer before an independent allocation-membership check. It cannot safely admit arbitrary corrupted intern pointers.'],
        requirements=['Register fully initialized scope and intern-object identities at native ownership handoff; reject foreign roots, parents and intern pointers before casting or dereferencing.',
                      'Capture or explicitly constrain names, type/subtype metadata, source locations, cell flag, time units/precision, scoped-time back-references and ordered intern membership.',
                      'Preserve complete child hierarchy and actual thread membership; bind known intern families to their existing payload observers. Pointer identity alone does not cover payloads.',
                      'Refuse unsupported scope subclasses, nonempty class maps, automatic hooks and live/free contexts under the static board profile.',
                      'Retain restored metadata/intern faults, original continuation, zero-output foreign-pointer refusal and allocation/lifecycle controls before board integration.',
                      'Audit all admitted runtime/VPI modules before relying on initialization-only invariants. The selected excerpts and textual call-site list alone are not an exhaustive nonmutation proof.'],
        scope='Pinned source ownership/consumer audit supporting the native scope counterexamples. No new observer, runtime write exclusion, operational board admission or general rollback claim.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args();result=assess(a.archive)
    if a.check:
        if json.loads(a.out.read_text())!=result:raise ValueError('Changed scope contract evidence')
    else:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('Scope metadata source contract verified; observer coverage remains open.')
