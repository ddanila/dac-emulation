"""Bind every final registered board signal to its native teardown operations."""
def validate(trace,rows):
    rows={r['pointer']:r for r in rows}
    if not rows:raise ValueError('Missing native board signals')
    begins=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_BEGIN ')]
    forgot=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_FORGET ')]
    released=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_RELEASED ')]
    if len(begins)!=len(rows) or {int(l[1],16) for l in begins}!=set(rows) or [l[1] for l in released]!=[l[1] for l in begins]:raise ValueError('Missing board signal destruction')
    if len(forgot)!=len(rows) or [l[1] for l in forgot]!=[l[1] for l in begins] or [(int(l[2]),int(l[3])) for l in forgot]!=[(n,n-1) for n in range(len(rows),0,-1)]:raise ValueError('Board signal registrations not drained')
    for a,b in zip(forgot,begins):
        row=rows[int(b[1],16)]
        if len(b)!=6 or (int(b[2],16),int(b[3],16),int(b[4]),int(b[5]))!=(row['node'],row['bits'],row['count'],0):raise ValueError('Wrong board signal release or open observation')
        i=trace.index(' '.join(b))
        if trace[i-1]!=' '.join(a) or trace[i+1]!='TEARDOWN_SIGNAL_RELEASED '+b[1]:raise ValueError('Wrong board signal cleanup order')
    pools=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_POOLS ')];frees=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_POOL_FREE ')];done=[l for l in trace if l.startswith('TEARDOWN_SIGNAL_POOLS_DONE ')]
    if len(pools)!=1 or done!=['TEARDOWN_SIGNAL_POOLS_DONE 0']:raise ValueError('Missing board signal pool cleanup')
    count,allocated,deleted,remaining,active=map(int,pools[0][1:])
    if not count or allocated!=len(rows) or deleted!=len(rows) or remaining or active or len(frees)!=count or [int(l[1]) for l in frees]!=list(range(count)) or len({l[2] for l in frees})!=count or any(int(l[2],16)==0 for l in frees):raise ValueError('Incomplete board signal pool free')
    if trace.index(' '.join(pools[0]))<=max(trace.index(' '.join(l)) for l in released) or trace.index(done[0])<=max(trace.index(' '.join(l)) for l in frees):raise ValueError('Wrong board pool cleanup order')
    return dict(nativeSignalsReleased=len(rows),nativeBitIndexesReleased=sum(r['count'] for r in rows.values()),nativePoolsFreed=count,remainingSignalRegistrations=0,observationClosedBeforeSignalRelease=True)
