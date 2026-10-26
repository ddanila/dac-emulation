"""Read-only, Darwin-specific mid-run memory observation; no full-run bound."""
import datetime,hashlib,json,platform,subprocess,sys
from pathlib import Path
ROOTS={1260:'refinement-6.25',1261:'refinement-12.5',1807:'instance-off',1808:'instance-check',1810:'instance-delayed',2890:'output-state-review'}
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(pids):
    return [json.loads(s) for s in subprocess.check_output([str(HERE/'footprint'),*map(str,pids)],text=True).splitlines()]

def control():
    code='''import sys,mmap
print("ready",flush=True);input()
a=mmap.mmap(-1,64*1024**2,flags=mmap.MAP_PRIVATE|mmap.MAP_ANON)
for i in range(0,len(a),4096):a[i]=1
print("allocated",flush=True);input()
a.close();print("released",flush=True);input()
'''
    p=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    samples=[]
    try:
        for stage in ('ready','allocated','released'):
            if p.stdout.readline().strip()!=stage:raise ValueError('Allocation control failed')
            samples.append(dict(stage=stage,**snapshot([p.pid])[0]))
            p.stdin.write('\n');p.stdin.flush()
        p.wait(timeout=10)
        if p.returncode:raise ValueError('Allocation child failed')
    finally:
        if p.poll() is None:p.kill();p.wait()
        p.stdin.close();p.stdout.close()
    a,b,c=samples
    assert a['startAbsoluteTime']==b['startAbsoluteTime']==c['startAbsoluteTime']
    assert b['footprintBytes']-a['footprintBytes']>=60*1024**2
    assert c['lifetimeMaximumFootprintBytes']>=b['footprintBytes']
    assert c['footprintBytes']<b['footprintBytes']-60*1024**2
    return samples

def main():
    validated=control()
    rows=[line.split(None,3) for line in subprocess.check_output(['ps','-axo','pid=,ppid=,rss=,args='],text=True).splitlines()]
    processes={int(pid):{'parent':int(parent),'rssKiB':int(rss),'command':cmd} for pid,parent,rss,cmd in rows}
    trees={}
    for root,label in ROOTS.items():
        if root not in processes:raise ValueError('Root already exited: '+label)
        selected={root}
        while True:
            more=selected|{pid for pid,p in processes.items() if p['parent'] in selected}
            if more==selected:break
            selected=more
        readings=snapshot(sorted(selected))
        for r in readings:
            if 'errno' in r or r['exitAbsoluteTime']:raise ValueError('Process exited while observing')
            r.update(processes[r['pid']])
        trees[label]={'rootPid':root,'processes':readings,'observedTreeFootprintBytes':sum(r['footprintBytes'] for r in readings)}
    result={'qualified':False,'scope':'Mid-run observation of identified live process trees. Individual kernel lifetime peaks extend to this query only. Sum of live footprints is not a simultaneous exact tree peak; exited descendants and future allocations are not covered. No memory cap, completed-run budget or full-repeat bound is established.',
            'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':platform.platform(),
            'api':'proc_pid_rusage RUSAGE_INFO_V4; memory fields in bytes; process start/exit identities in absolute-time units',
            'source':'https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/resource.h',
            'sources':{n:sha(HERE/n) for n in ('footprint.c','observe.py')},'binarySha256':sha(HERE/'footprint'),'compileCommand':['cc','-Wall','-Wextra','-Werror','-O2','footprint.c','-o','footprint'],
            'sdkHeaderSha256':sha(Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/resource.h')),
            'allocationControl':validated,'trees':trees}
    (HERE/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    for label,tree in trees.items():print(label,round(tree['observedTreeFootprintBytes']/1024**2,2),'MiB')
if __name__=='__main__':main()
