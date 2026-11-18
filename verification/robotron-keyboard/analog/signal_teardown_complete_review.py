"""Replay complete signal teardown and reconstruct the exact source change."""
import json,tempfile
from pathlib import Path
from signal_teardown_review import review as trace_review
from build_signal_teardown_trace_runtime import instrument
from build_signal_teardown_clear_runtime import invalidate
from ttl7406_probe import sha

def review(root):
    kind=json.loads((root/'source-chain.json').read_text())['kind']
    if kind not in ('trace','clear'):raise ValueError('Unknown signal teardown candidate')
    parent=json.loads((root/'parent-build.json').read_text());build=json.loads((root/'build.json').read_text())
    if sha(root/'before-source.cc')!=parent['outputs']['vvp/vpi_signal.cc'] or sha(root/'after-source.cc')!=build['outputs']['vvp/vpi_signal.cc']:raise ValueError('Changed selected signal source')
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory);(target/'vvp').mkdir();(target/'vvp/vpi_signal.cc').write_bytes((root/'before-source.cc').read_bytes())
        (instrument if kind=='trace' else invalidate)(target)
        if (target/'vvp/vpi_signal.cc').read_bytes()!=(root/'after-source.cc').read_bytes():raise ValueError('Unexpected signal teardown source change')
    result=trace_review(root)
    lines=(root/'enabled.stdout').read_text().splitlines();forgot=[l.split() for l in lines if l.startswith('TEARDOWN_SIGNAL_FORGET ')];begins=[l.split() for l in lines if l.startswith('TEARDOWN_SIGNAL_BEGIN ')]
    if kind=='trace':
        if forgot or result['remainingSignalRegistrations']!=9:raise ValueError('Changed diagnostic-only lifecycle')
    else:
        if len(forgot)!=9 or result['remainingSignalRegistrations']!=0:raise ValueError('Signal registrations not cleared')
        if [l[1] for l in forgot]!=[l[1] for l in begins] or [(int(l[2]),int(l[3])) for l in forgot]!=[(n,n-1) for n in range(9,0,-1)]:raise ValueError('Incomplete native registration drainage')
        for a,b in zip(forgot,begins):
            if lines.index(' '.join(a))+1!=lines.index(' '.join(b)):raise ValueError('Registration not removed before native release')
    return dict(result,sourceChangeExactlyReconstructed=True,candidateKind=kind)
