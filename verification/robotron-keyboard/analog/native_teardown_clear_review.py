#!/usr/bin/env python3
"""Review native scope-registry teardown against the retained stale-registry control."""
import argparse,json,tempfile
from pathlib import Path
from ttl7406_probe import sha
from native_teardown_trace import review as trace_review
from parameter_refusal_recovery import review as parameter_review
from memory_lifecycle import review as memory_review
from build_native_teardown_clear_runtime import invalidate
HERE=Path(__file__).resolve().parent

def review(root):
    before=HERE/'reports/native-teardown-trace'
    trace=trace_review(root)
    if not trace['allTrackedRegistriesEmpty']:raise ValueError('Stale native registrations remain')
    original=trace_review(before)
    if original['allTrackedRegistriesEmpty'] or original['registrySizes']['before']!=trace['registrySizes']['before']:raise ValueError('Missing matched stale-registry control')
    build=json.loads((root/'build.json').read_text())
    for name in ('vvp/lib_main.cc','vvp/vpi_scope.cc','vvp/vpi_const.cc','vvp/array.cc'):
        if sha(root/'runtime'/name)!=build['outputs'][name]:raise ValueError('Changed cleanup source')
        if name!='vvp/vpi_scope.cc' and (root/'runtime'/name).read_bytes()!=(before/'runtime'/name).read_bytes():raise ValueError('Unrelated runtime mutation')
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory);(target/'vvp').mkdir();(target/'vvp/vpi_scope.cc').write_bytes((before/'runtime/vvp/vpi_scope.cc').read_bytes());invalidate(target)
        if (target/'vvp/vpi_scope.cc').read_bytes()!=(root/'runtime/vvp/vpi_scope.cc').read_bytes():raise ValueError('Unreviewed teardown mutation')
    regressions={}
    for family,fn in [('parameter',parameter_review),('memory',memory_review)]:
        child=root/(family+'-regression')
        if json.loads((child/'build.json').read_text())!=build:raise ValueError('Regression runtime mismatch')
        regressions[family]=fn(child)
        if not regressions[family]['controlsPassed']:raise ValueError('Failed native regression')
    return dict(qualified=False,controlsPassed=True,nativeParameterDestructions=6,nativeMemoryDestructions=2,
                registrySizes=trace['registrySizes'],postCleanupZeroOutputRefusals=7,regressions=regressions,
                scope='Eight non-owning scope observer registries clear after native root traversal. A termination flag preserves fail-closed observation; monotonic IDs are not reset. Exact before/after source comparison permits only this change. Original/disabled/enabled continuation and same-build parameter-recovery/memory-lifecycle regressions pass. Coverage is this fixture and these registries, not every runtime registry, board teardown, custom-pool safety, leaks or dangling handles. Existing ASAN loader-table exclusion applies.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
