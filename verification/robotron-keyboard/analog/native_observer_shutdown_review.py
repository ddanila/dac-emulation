"""Review the native final-cleanup guard and matched 55-inventory sweep."""
import json,shutil,tempfile
from pathlib import Path
from ttl7406_probe import sha
from native_observer_shutdown_sweep import review as sweep_review
from build_native_observer_shutdown_runtime import guard

def review(root):
    before=sweep_review(root/'before');after=sweep_review(root/'after')
    if before['inventories']!=55 or set(before['results'])!=set(after['results']) or before['sanitizerFailures']!=15:raise ValueError('Missing matched failure controls')
    if after['sanitizerFailures'] or after['postRefusals']!=55 or after['postAcceptances']:raise ValueError('Unsafe post-cleanup inventory')
    for name,result in after['results'].items():
        if result['exitCode'] or not result['stderrEmpty'] or not result['postEntered'] or not result['postReturned']:raise ValueError('Incomplete guarded execution')
        for phase in ('start','end'):
            if result['phases'][phase]['returnCode']!=before['results'][name]['phases'][phase]['returnCode']:raise ValueError('Changed pre-cleanup admission')
    for name in ('probe.v','probe.cc'):
        if (root/'before'/name).read_bytes()!=(root/'after'/name).read_bytes():raise ValueError('Different sweep fixtures')
    hdl=[]
    for phase in ('before','after'):
        receipt=json.loads((root/phase/'run.json').read_text())
        fixture=receipt['commands'][0][-1]
        hdl.append((root/phase/'baseline.stdout').read_text().replace(fixture,'PROBE.v'))
    if hdl[0]!=hdl[1]:raise ValueError('Changed baseline continuation across builds')
    builds={phase:json.loads((root/phase/'build.json').read_text()) for phase in ('before','after')}
    receipts={phase:json.loads((root/phase/'run.json').read_text()) for phase in ('before','after')}
    for phase in ('before','after'):
        for path in (root/(phase+'-source')).rglob('*.cc'):
            name=str(path.relative_to(root/(phase+'-source')))
            expected=builds[phase]['outputs'].get(name,receipts[phase]['inventorySources'].get(name))
            if not expected or sha(path)!=expected:raise ValueError('Changed guard source')
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory)/'runtime';shutil.copytree(root/'before-source',target);guard(target)
        expected={str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
        actual={str(p.relative_to(root/'after-source')):p.read_bytes() for p in (root/'after-source').rglob('*') if p.is_file()}
        if expected!=actual:raise ValueError('Unreviewed native guard mutation')
    sites=json.loads((root/'after-source/observer-shutdown-sites.json').read_text());names=[n for group in sites.values() for n in group]
    if len(names)!=55 or set(names)!=set(after['results']):raise ValueError('Incomplete guard coverage')
    return dict(qualified=False,controlsPassed=True,guardedEntryPoints=55,postCleanupZeroOutputRefusals=55,priorSanitizerFailures=15,
                unchangedPreCleanupReturnCodes=True,sourceTransformationExactlyMatched=True,
                scope='The lifecycle flag closes all 55 exported native inventory entry points before final cleanup touches storage. All 55 isolated processes return -1 with zero output after cleanup; previous 15 ASAN failures and 13 post-cleanup acceptances are eliminated. Before/end admission return codes and HDL continuation remain unchanged in this fixture. Source changes match only the shared flag and guards. This is not registry emptiness, arbitrary getter/mutator safety, concurrent observation, all-family payload coverage, runtime reuse, or integrated-board qualification of this revision. ASAN loader-table exclusions and disabled leak/custom-pool checks remain.')
