#!/usr/bin/env python3
"""Extract remaining scope-owned signal, parameter and memory payload contracts."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def assess(archive):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed native archive')
    paths=('vvp/vpi_priv.h','vvp/vpi_signal.cc','vvp/vpi_const.cc','vvp/array.cc');sources={}
    with tarfile.open(archive) as tar:
        for path in paths:
            found=[m for m in tar.getmembers() if m.name.endswith('/'+path)]
            if len(found)!=1:raise ValueError('Missing native source')
            sources[path]=tar.extractfile(found[0]).read().decode()
    def section(path,start,end):
        text=sources[path];a=text.rindex(start) if start.startswith('static vpiHandle fill_in_net4(') else text.index(start);b=text.index(end,a+len(start))
        return dict(file=path,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    evidence=dict(signalFields=section('vvp/vpi_priv.h','struct __vpiSignal :','extern unsigned vpip_size'),
        signalInitialization=section('vvp/vpi_signal.cc','static vpiHandle fill_in_net4(struct __vpiSignal*obj, __vpiScope*scope,\n','vpiHandle vpip_make_net4('),
        binaryConstantFields=section('vvp/vpi_priv.h','struct __vpiBinaryConst :','vpiHandle vpip_make_binary_const('),
        binaryParameterFieldsAndInitialization=section('vvp/vpi_const.cc','struct __vpiBinaryParam','__vpiBinaryParam::~__vpiBinaryParam()'),
        binaryParameterConsumers=section('vvp/vpi_const.cc','int __vpiBinaryParam::get_type_code','vpiHandle vpip_make_binary_param('),
        arrayFields=section('vvp/vpi_priv.h','struct __vpiArray :','class __vpiDarrayVar :'))
    # The definition, rather than the earlier prototype, is required above.
    if 'obj->within.scope = scope;' not in evidence['signalInitialization']['excerpt']:raise ValueError('Missing signal initialization definition')
    patches={n:(HERE/'engine-patches'/n).read_text() for n in ('icarus-signal-handles.patch','icarus-signal-scope-scan.patch','icarus-array-observer.patch')}
    return dict(qualified=False,completed=True,archiveSha256=ARCHIVE_SHA,
        nativeSources={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()},evidence=evidence,observerPatches=patches,
        findings=['Signal handles contain signedness, declaration ranges, name/array-index and owner unions, net reference and lazy bit cache. Existing VSH loops select admitted entries, not every registered or scope-owned signal.',
            'Binary parameter handles inherit mutable vector bits and signed/sized flags, and carry private scope/name/local/source metadata. Scope object identity and type do not encode those fields.',
            'Static array snapshots include storage values, ranges, dimensions, ownership and lazy word-cache pointers, but omit the native memory name. Existing array collection casts scope intern entries before separate allocation admission.',
            'The retained native fixture changes an unadmitted signal sign, parameter bit and memory name; each changes a VPI consumer while all five tested images remain identical. This does not demonstrate ordinary runtime writes.'],
        requirements=['Bind every scope-owned signal to its initialized native allocation and net identity; distinguish bridge admission from whole-scope coverage and distinguish array-word union arms.',
            'Record exact supported signal families and bounded names before any later dereference. Capture signedness/ranges and lazy bit identities; qualify growth and deletion/address reuse independently.',
            'Register initialized parameter allocations, exact string/binary/real families, names and storage bounds. Capture raw values and metadata or prove justified invariants for every admitted runtime module; do not infer immutability from Verilog parameter syntax.',
            'Join each memory scope-object identity to its existing array inventory, add bounded memory names, and validate allocation families before casts or dereferences. Preserve complete array values and caches.',
            'Retain exact restoration, original-runtime continuation and negative controls; qualify board populations, compact encoding and full transient cost before extending operational acceptance.'],
        scope='Selected pinned source excerpts plus existing observer patches identify remaining scope payload requirements. No exhaustive write exclusion, new observer, safety proof for array traversal or operational qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args();r=assess(a.archive)
    if a.check:
        if r!=json.loads(a.out.read_text()):raise ValueError('Changed scope payload contract')
    else:a.out.write_text(json.dumps(r,indent=2)+'\n')
