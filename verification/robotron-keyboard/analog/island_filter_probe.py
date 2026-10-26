#!/usr/bin/env python3
"""Exercise live island wire filters across whole/partial and linked force/release."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from island_probe import differences
HERE=Path(__file__).resolve().parent


def parse_snapshot(lines):
    a=lines[0].split();z=lines[-1].split()
    if len(a)!=3 or a[:2]!=['VIF_BEGIN','1'] or len(z)!=2 or z[0]!='VIF_END':raise ValueError('Invalid filter framing')
    tick=int(a[2]);ports=[];i=1;keys=set();pointers=set()
    ptr=lambda v:0 if v=='(nil)' else int(v,16)
    while i<len(lines)-1:
        a=lines[i].split();i+=1
        if len(a)!=4 or a[0]!='VIF_PORT':raise ValueError('Missing filter port')
        island,port=map(int,a[1:3]);pointer=ptr(a[3])
        if min(island,port,pointer)<1 or (island,port) in keys or pointer in pointers:raise ValueError('Missing/aliased filter identity')
        keys.add((island,port));pointers.add(pointer)
        a=lines[i].split();i+=1
        if len(a)!=2 or a[0]!='VIF_WIRE' or a[1] not in ('0','1'):raise ValueError('Invalid initialization flag')
        record=dict(island=island,port=port,pointer=pointer,init=int(a[1]))
        a=lines[i].split();i+=1
        if len(a)!=5 or a[0]!='VIF_BASE' or a[1] not in ('0','1'):raise ValueError('Missing base state')
        size=int(a[3]);bits=a[4]
        if size<0 or (not size and bits!='-') or (size and (len(bits)!=size or any(c not in '01' for c in bits))):raise ValueError('Invalid force mask')
        record.update(propagate=int(a[1]),linkPointer=ptr(a[2]),mask=dict(size=size,bits=bits),link=None,vectors={})
        if record['linkPointer']:
            a=lines[i].split();i+=1
            if len(a)!=5 or a[0]!='VIF_LINK':raise ValueError('Missing initialized link fields')
            source,destination=ptr(a[1]),ptr(a[3]);sp,dp=int(a[2]),int(a[4])
            if min(source,destination)<0 or sp not in range(4) or dp not in range(4):raise ValueError('Invalid link endpoints')
            record['link']=dict(source=source,sourcePort=sp,destination=destination,destinationPort=dp)
        for name in ('driven','forced'):
            a=lines[i].split();i+=1
            if len(a)!=4 or a[:2]!=['VIF_VECTOR',name]:raise ValueError('Missing filter vector')
            size=int(a[2]);bits=a[3]
            if size<0 or (not size and bits!='-') or (size and (len(bits)!=size*3 or any(c not in '0123' for c in bits[::3]) or any(c not in '01234567' for c in bits[1::3]+bits[2::3]))):raise ValueError('Invalid filter strength vector')
            record['vectors'][name]=dict(size=size,bits=bits)
        ports.append(record)
    if tick<0 or i!=len(lines)-1 or len(ports)!=int(z[1]):raise ValueError('Invalid filter footer')
    return dict(tick=tick,ports=ports)


def target(snapshot,field):
    for i,p in enumerate(snapshot['ports']):
        if field==0:return ('ports',i,'init')
        if field==4:return ('ports',i,'propagate')
        if field==5 and p['linkPointer']:return ('ports',i,'link','destinationPort')
        if field==3 and p['mask']['size']:return ('ports',i,'mask','bits')
        if field in (1,2,6):
            name='forced' if field==2 else 'driven'
            if p['vectors'][name]['size']:return ('ports',i,'vectors',name,'bits')
    return None


def changed_snapshot(before,changed,field):
    path=target(before,field)
    if path is None or differences(before,changed)!=[path]:raise ValueError('Wrong filter fault or unrelated state change')
    a,b=before,changed
    for key in path:a=a[key];b=b[key]
    if field in (0,4,5):expected=a^1
    elif field==3:expected=('1' if a[0]=='0' else '0')+a[1:]
    elif field in (1,2):expected=('0' if a[0]=='1' else '1')+'66'+a[3:]
    else:
        value,s0,s1=map(int,a[:3]);s0^=1;s1^=1
        if value==0:s1=s0
        elif value==1:s0=s1
        elif value==2:s0=s1=0
        expected=str(value)+str(s0)+str(s1)+a[3:]
    if b!=expected:raise ValueError('Wrong filter field mutation')


def fixture_state(snapshot,stage):
    if snapshot['tick']!=(stage+1)*1000 or len(snapshot['ports'])!=2:raise ValueError('Wrong fixture time/scope')
    a,b=snapshot['ports'];values=('1010','0011','0010','0010','0101','1100','1010','1100','1010')
    bits=lambda v:''.join('01zx'[int(c)] for c in v['bits'][::3])[::-1] if v['size'] else ''
    masks=('-', '1111','1111','0111','1111','1111','-','1111','-')
    if a['mask']['bits']!=masks[stage] or b['mask']['size'] or b['link'] is not None:raise ValueError('Wrong whole/partial force mask')
    for p in (a,b):
        if p['init'] or p['propagate'] or bits(p['vectors']['driven'])!=values[stage]:raise ValueError('Wrong initialized drive state')
        if any(c!='6' for c in p['vectors']['driven']['bits'][1::3]+p['vectors']['driven']['bits'][2::3]):raise ValueError('Changed fixture strength')
    if a['mask']['size'] and bits(a['vectors']['forced'])!=values[stage]:raise ValueError('Wrong active forced value')
    if stage<4:
        if a['link'] is not None:raise ValueError('Unexpected constant-force link')
    else:
        link=a['link']
        if not link or not link['destination'] or link['sourcePort'] or link['destinationPort']:raise ValueError('Missing linked-force destination')
        if bool(link['source'])!=(stage in (4,5,7)):raise ValueError('Wrong force-link/unlink state')
    return [(p['island'],p['port'],p['pointer']) for p in (a,b)]


def review(root):
    expected=['CHANGE 0 1010 1010','CHANGE 1000 0011 0011','CHANGE 2000 0010 0010',
              'CHANGE 3000 0010 0010','CHANGE 4000 0101 0101','CHANGE 5000 1100 1100',
              'CHANGE 6000 1010 1010','CHANGE 7000 1100 1100','CHANGE 8000 1010 1010']
    output=None;trajectory=None;faults={i:0 for i in range(7)}
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        lines=(root/(mode+'.stdout')).read_text().splitlines();normal=[l for l in lines if not l.startswith(('VIF_','VFM_'))]
        if [l for l in normal if l.startswith('CHANGE ')]!=expected:raise ValueError('Wrong force/release behavior')
        if output is None:output=normal
        elif output!=normal:raise ValueError('Changed complete simulator output')
        controls=[l for l in lines if l.startswith(('VIF_','VFM_'))];cursor=0;snapshots=[];layout=None;link_identity=None;pointers={}
        def consume(line):
            nonlocal cursor
            if cursor>=len(controls) or controls[cursor]!=line:raise ValueError('Missing/reordered record: '+line)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(controls) and not controls[cursor].startswith('VIF_END '):cursor+=1
            if cursor==len(controls):raise ValueError('Truncated filter snapshot')
            cursor+=1;return parse_snapshot(controls[start:cursor])
        def pointer(n):
            if not n:return 0
            if n not in pointers:pointers[n]=len(pointers)+1
            return pointers[n]
        for stage in range(9):
            consume(f'VFM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VFM_BEFORE');before=snapshot();current=fixture_state(before,stage)
                if layout is None:layout=current
                elif layout!=current:raise ValueError('Changed filter identity')
                if stage>=4:
                    a=before['ports'][0];current=(a['linkPointer'],a['link']['destination'])
                    if link_identity is None:link_identity=current
                    elif link_identity!=current:raise ValueError('Changed force-link lifetime')
                consume('VFM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed filter state')
                normalized=copy.deepcopy(before)
                for p in normalized['ports']:
                    for key in ('pointer','linkPointer'):p[key]=pointer(p[key])
                    if p['link']:
                        for key in ('source','destination'):p['link'][key]=pointer(p['link'][key])
                snapshots.append(normalized)
                if mode=='corrupt':
                    for field in range(7):
                        if target(before,field) is None:continue
                        consume(f'VFM_CHANGED {field}');changed_snapshot(before,snapshot(),field)
                        consume('VFM_RESTORED')
                        if snapshot()!=before:raise ValueError('Filter fault not restored')
                        consume(f'VFM_FAULT {field} 1 1');faults[field]+=1
            consume(f'VFM_DONE {stage}')
        if cursor!=len(controls):raise ValueError('Unexpected observer record')
        if snapshots:
            if trajectory is None:trajectory=snapshots
            elif trajectory!=snapshots:raise ValueError('Faults changed normal filter trajectory')
    if not all(faults.values()):raise ValueError('Missing filter fault family')
    return dict(completed=True,qualified=False,simulationOutputExactlyEqual=True,restoredFaults=sum(faults.values()),faultsByField=faults,
                scope='Island vec8 wire-filter caches, force masks, initialization/propagation flags and initialized force-link endpoints across whole/partial and linked force/release. All injected field changes restored before continuation.',
                notEstablished=['Combined board integration','Value-callback lists and net fanout referents','Thread state, freed-storage equivalence and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/island_filter_probe.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_FILTER_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_filter_probe.py','fixtures/island_filter_probe.c','fixtures/island_filter_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Island force/filter controls verified; board and remaining referents stay open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
