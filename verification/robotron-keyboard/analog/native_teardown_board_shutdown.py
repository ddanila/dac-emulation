"""Validate board-native destruction and post-cleanup refusal from the complete log."""
import json
from pathlib import Path
from parameter_compact import ParameterDecoder
from memory_compact import MemoryDecoder
from parameter_payload import parse as parameter_parse
from memory_metadata import parse as memory_parse
from trace_io import open_text

def review(folder):
    decoders={'VPMD':ParameterDecoder(),'VMMD':MemoryDecoder()};last={};active=None;block=[];trace=[];post=[];started=False;ended=False
    with open_text(folder/'ngspice.log') as stream:
        for raw in stream:
            line=raw.rstrip('\n')
            if 'AddressSanitizer' in line:raise ValueError('Sanitizer diagnostic in board execution')
            if active:
                block.append(line)
                if line==active+'_END':
                    dense=decoders[active].decode(block);last[active]={'VPMD':parameter_parse,'VMMD':memory_parse}[active](dense.splitlines());active=None;block=[]
                continue
            if line.startswith(('VPMD_BEGIN ','VMMD_BEGIN ')):
                if started:raise ValueError('Observer image after native cleanup began')
                active=line.split('_BEGIN')[0];block=[line];continue
            if line=='TEARDOWN_BEGIN':
                if started:raise ValueError('Repeated native cleanup')
                started=True
            if line.startswith('TEARDOWN_') and started:
                if ended:raise ValueError('Native cleanup trace after unload')
                trace.append(line)
                if line=='TEARDOWN_UNLOAD':ended=True
            if line.startswith(('POST_CLEANUP_','POST_RESULT ')):
                if not ended:raise ValueError('Post-cleanup probe before native unload')
                post.append(line)
    if active or set(last)!={'VPMD','VMMD'} or any(d.sequence!=6 for d in decoders.values()):raise ValueError('Incomplete final board inventories')
    if not started or not ended or trace[0]!='TEARDOWN_BEGIN' or trace[-1]!='TEARDOWN_UNLOAD':raise ValueError('Incomplete native board cleanup')
    parameters=last['VPMD']['rows'];memories=last['VMMD']['rows']
    if len(parameters)!=56 or len(memories)!=3:raise ValueError('Wrong compiled board population')
    rows=[line.split() for line in trace if line.startswith('TEARDOWN_PARAMETER ')]
    if len(rows)!=56 or {(int(p,16),kind.lower()) for _,kind,p in rows}!={(r['pointer'],r['kind']) for r in parameters}:raise ValueError('Missing board parameter destruction')
    remaining=[int(line.split()[1]) for line in trace if line.startswith('TEARDOWN_PARAMETER_REMAIN ')]
    if remaining!=list(range(55,-1,-1)):raise ValueError('Board parameter registry not drained')
    rows=[line.split() for line in trace if line.startswith('TEARDOWN_MEMORY ')]
    if len(rows)!=3 or {int(p,16) for _,p,_ in rows}!={r['array'] for r in memories} or [int(n) for _,_,n in rows]!=[2,1,0]:raise ValueError('Board memory registry not drained')
    rows=[line.split() for line in trace if line.startswith('TEARDOWN_REGISTRIES ')]
    if len(rows)!=2 or [r[1] for r in rows]!=['before','after'] or any(len(r)!=11 for r in rows) or len(trace)!=119:raise ValueError('Incomplete board registry trace')
    keys=['roots','initializedScopes','scopeMetadata','attachedObjects','objectIds','objectTypes','ports','portSlots','portBits'];sizes={r[1]:dict(zip(keys,map(int,r[2:]))) for r in rows}
    if sizes['before']['initializedScopes']!=32 or sizes['before']['scopeMetadata']!=32 or any(sizes['after'].values()):raise ValueError('Stale board scope registration')
    names=['scope_metadata','scope_metadata_reference','parameter','memory_metadata','array','array_compact','port_payload']
    expected=['POST_CLEANUP_ENTER']+['POST_RESULT robotron_vvp_'+n+'_inventory -1 0' for n in names]+['POST_CLEANUP_RETURN']
    if post!=expected:raise ValueError('Missing exact board post-cleanup refusals')
    receipt=json.loads((folder/'run.json').read_text());env=receipt['runtimeEnvironment']
    if env.get('ASAN_OPTIONS')!='halt_on_error=1:abort_on_error=0:detect_leaks=0' or receipt['environment'].get('ROBOTRON_TEARDOWN_TRACE')!='1':raise ValueError('Changed sanitizer/trace environment')
    sanitizer=env.get('DYLD_INSERT_LIBRARIES')
    if not sanitizer or len([d for d in receipt['externalDependencies'] if d['path']==sanitizer])!=1:raise ValueError('Unpinned sanitizer runtime')
    return dict(nativeParameterDestructions=56,nativeMemoryDestructions=3,registrySizes=sizes,postCleanupZeroOutputRefusals=7)
