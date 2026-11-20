"""Hash-verified completed electrical traces; never simulator checkpoints."""
import hashlib
import errno
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
from file_hash import digest
import monitor_runtime
import steady_supply


def validate(entry,text,deadline=None):
    manifest=json.loads((entry/'cache.json').read_text())
    if manifest.get('format')!='dac-electrical-trace-cache-v1':raise ValueError('unsupported electrical cache')
    if set(manifest['files'])!={'run.cir','trace.raw','solve.json','solver.log','process.log'}:
        raise ValueError('invalid electrical cache file set')
    for name,value in manifest['files'].items():
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('electrical cache verification deadline')
        if digest(entry/name)!=value:raise ValueError('electrical cache hash mismatch: '+name)
    if (entry/'run.cir').read_text()!=text:raise ValueError('electrical cache deck mismatch')
    solve=json.loads((entry/'solve.json').read_text())
    if solve['status']!='complete':raise ValueError('incomplete electrical solve cannot be cached')
    match=re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',text)
    if not match:raise ValueError('cache requires explicit transient endpoint')
    end=float(match[1]);last=None
    for i,row in enumerate(steady_supply.raw_rows(entry/'trace.raw')):
        if i%10000==0 and deadline is not None and time.monotonic()>=deadline:raise TimeoutError('electrical cache verification deadline')
        last=row['time']
    if last is None or abs(last-end)>max(1e-12,abs(end)*1e-10):raise ValueError('cached trace is truncated')
    return solve,manifest


def solve(text,output,runtime,*,timeout_s,cache=None):
    if cache is None:return steady_supply.solve(text,output,runtime,timeout_s=timeout_s)
    begin=time.monotonic();out=Path(output).resolve();root=Path(cache).resolve()
    _,receipt=monitor_runtime.verify(runtime)
    key_inputs=dict(format='dac-electrical-trace-cache-v1',deck_sha256=hashlib.sha256(text.encode()).hexdigest(),runtime=receipt)
    key=hashlib.sha256(json.dumps(key_inputs,sort_keys=True).encode()).hexdigest()
    entry=root/key
    if entry.exists():
        solved,manifest=validate(entry,text,begin+timeout_s)
        if time.monotonic()-begin>=timeout_s:raise TimeoutError('electrical cache verification exceeded trial deadline')
        out.mkdir(parents=True,exist_ok=False)
        for name in manifest['files']:shutil.copyfile(entry/name,out/name)
        # Verify copied artifacts too; a cache hit never imports prior acceptance.
        shutil.copyfile(entry/'cache.json',out/'cache.json');validate(out,text,begin+timeout_s)
        result=dict(solved,cache_hit=True,cache_key=key,cache_verified=True,
                    cached_solver_elapsed_s=solved['elapsed_s'],elapsed_s=time.monotonic()-begin)
        (out/'cache-use.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    remaining=timeout_s-(time.monotonic()-begin)
    if remaining<=0:raise TimeoutError('electrical cache lookup exhausted trial deadline')
    result=steady_supply.solve(text,out,runtime,timeout_s=remaining)
    if result['status']!='complete':return result
    root.mkdir(parents=True,exist_ok=True)
    files=('run.cir','trace.raw','solve.json','solver.log','process.log')
    manifest=dict(key_inputs,files={name:digest(out/name) for name in files},
                  electrical_acceptance_reused=False,checkpoint=False)
    with tempfile.TemporaryDirectory(prefix='pending-',dir=root) as temporary:
        staging=Path(temporary)/'artifact';staging.mkdir()
        for name in files:shutil.copyfile(out/name,staging/name)
        (staging/'cache.json').write_text(json.dumps(manifest,indent=2)+'\n')
        validate(staging,text)
        if entry.exists():validate(entry,text)
        else:
            try:staging.rename(entry)
            except OSError as error:
                if error.errno not in (errno.EEXIST,errno.ENOTEMPTY):raise
                validate(entry,text)
    return dict(result,cache_hit=False,cache_key=key,cache_verified=True)
