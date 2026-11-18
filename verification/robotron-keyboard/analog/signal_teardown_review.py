"""Bind native signal cleanup to complete final signal and bit-cache inventories."""
import json,re
from pathlib import Path
from signal_handles import parse

def review(root):
    receipt=json.loads((root/'run.json').read_text());streams={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native signal teardown run')
        streams[mode]=(root/(mode+'.stdout')).read_text()
    text=streams['enabled'];images={}
    for reason,name,body in re.findall(r'OBSERVER_BEGIN (\d+) (\w+)\n(.*?)OBSERVER_END\n',text,re.S):
        key=(int(reason),name)
        if key in images:raise ValueError('Repeated signal image')
        if name=='robotron_vvp_scope_signal_inventory':body=body.replace('VSA_','VSH_')
        elif name!='robotron_vvp_signal_handle_inventory':raise ValueError('Unexpected inventory')
        images[key]=parse(body.splitlines())
    expected={(r,'robotron_vvp_'+n+'_inventory') for r in (11,12) for n in ('signal_handle','scope_signal')}
    if set(images)!=expected:raise ValueError('Missing full signal images')
    start=images[11,'robotron_vvp_signal_handle_inventory'];end=images[12,'robotron_vvp_signal_handle_inventory'];all_signals=images[12,'robotron_vvp_scope_signal_inventory']
    if start['tick']!=0 or end['tick']!=5000 or start['rows']!=end['rows']:raise ValueError('Signal lifetime/cache changed before cleanup')
    if images[11,'robotron_vvp_scope_signal_inventory']['rows']!=all_signals['rows']:raise ValueError('Native population changed before cleanup')
    bindings=re.findall(r'^SIGNAL_BIND (\S+) (\d+) (\S+) (\S+) (\S+)$',text,re.M)
    if len(bindings)!=9 or len({b[0] for b in bindings})!=9:raise ValueError('Incomplete signal handoff')
    rows={r['pointer']:r for r in all_signals['rows']}
    if len(rows)!=9 or start['rows']!=all_signals['rows']:raise ValueError('Missing complete native signal population')
    for name,serial,pointer,left,right in bindings:
        row=rows[int(pointer,16)]
        if row['id']!=int(serial) or bytes.fromhex(row['name']).decode()!=name.split('.')[-1]+'\0':raise ValueError('Wrong signal binding')
        if row['count']!=abs(row['msb']-row['lsb'])+1 or not row['cache']:raise ValueError('Missing allocated bit cache')
        if int(left,16)!=row['cache'][-1]['pointer'] or int(right,16)!=row['cache'][0]['pointer']:raise ValueError('Wrong endpoint cache binding')
    lines=text.splitlines();trace=[l for l in lines if l.startswith('TEARDOWN_')]
    begins=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_BEGIN ')];released=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_RELEASED ')]
    if len(begins)!=len(rows) or {int(l[1],16) for l in begins}!=set(rows) or [l[1] for l in released]!=[l[1] for l in begins]:raise ValueError('Missing native signal release')
    for line in begins:
        if len(line)!=6:raise ValueError('Malformed signal release')
        row=rows[int(line[1],16)]
        if (int(line[2],16),int(line[3],16),int(line[4]),int(line[5]))!=(row['node'],row['bits'],row['count'],0):raise ValueError('Wrong signal/cache release or open observation')
        i=trace.index(' '.join(line))
        if trace[i+1]!='TEARDOWN_SIGNAL_RELEASED '+line[1]:raise ValueError('Incomplete native release ordering')
    pools=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_POOLS ')];frees=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_POOL_FREE ')];done=[l.split() for l in trace if l.startswith('TEARDOWN_SIGNAL_POOLS_DONE ')]
    if len(pools)!=1 or len(done)!=1:raise ValueError('Missing native pool cleanup')
    count,allocated,deleted,remaining,active=map(int,pools[0][1:])
    if not count or allocated!=9 or deleted!=9 or active or len(frees)!=count or [int(l[1]) for l in frees]!=list(range(count)) or len({l[2] for l in frees})!=count or any(int(l[2],16)==0 for l in frees):raise ValueError('Incomplete native pool free')
    if int(done[0][1])!=remaining:raise ValueError('Inconsistent remaining registration count')
    if trace.index(' '.join(pools[0]))<=max(trace.index(' '.join(l)) for l in released) or trace.index(' '.join(done[0]))<=max(trace.index(' '.join(l)) for l in frees):raise ValueError('Wrong pool cleanup order')
    suffix='POST_CLEANUP_ENTER\n'+''.join('POST_RESULT robotron_vvp_'+n+'_inventory -1 0\n' for n in ('signal_handle','scope_signal'))+'POST_CLEANUP_RETURN\n'
    if not text.endswith(suffix) or not trace or trace[0]!='TEARDOWN_BEGIN' or trace[-1]!='TEARDOWN_UNLOAD':raise ValueError('Missing post-cleanup refusal')
    if lines.index('TEARDOWN_BEGIN')<=max(i for i,l in enumerate(lines) if l=='OBSERVER_END') or lines.index('TEARDOWN_UNLOAD')>=lines.index('POST_CLEANUP_ENTER'):raise ValueError('Wrong observation lifetime ordering')
    stripped=re.sub(r'OBSERVER_BEGIN .*?OBSERVER_END\n','',text,flags=re.S)
    stripped=''.join(l+'\n' for l in stripped[:-len(suffix)].splitlines() if not l.startswith(('TEARDOWN_','SIGNAL_BIND ')))
    if stripped!=streams['baseline'] or stripped!=streams['disabled'] or 'CONTINUE ' not in stripped:raise ValueError('Changed HDL continuation')
    return dict(qualified=False,controlsPassed=True,nativeSignalsReleased=len(rows),nativeBitIndexesReleased=sum(r['count'] for r in rows.values()),nativePoolsFreed=count,remainingSignalRegistrations=remaining,allSignalRegistrationsCleared=remaining==0,observationClosedBeforeSignalRelease=True,postCleanupZeroOutputRefusals=2,originalContinuationExactlyEqual=True,scope='Complete nine-signal native fixture population, allocated bit/index caches and graph nodes traverse native signal_delete before pool free; observation is closed throughout teardown. Remaining non-owning registrations are reported without dereferencing freed storage. ASAN leak detection and Valgrind pool annotations are disabled. No board teardown, arbitrary handle deletion, dangling-handle access, pool reuse or custom-pool memory safety claim.')
