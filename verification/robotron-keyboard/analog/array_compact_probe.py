#!/usr/bin/env python3
"""Reconstruct compact array images and compare every native observation exactly."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import array_probe as dense
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def expand(lines):
    if not lines or not lines[0].startswith('VAC_BEGIN 1 '):raise ValueError('Missing compact header')
    result=[lines[0].replace('VAC_BEGIN','VAR_BEGIN',1)];i=1
    while i<len(lines) and lines[i].startswith('VAR_ARRAY '):
        metadata=lines[i].split()
        if len(metadata)!=15:raise ValueError('Invalid compact array metadata')
        size,width=int(metadata[9]),int(metadata[10])
        if size<=0 or width<=0:raise ValueError('Invalid compact dimensions')
        result.append(lines[i]);i+=1
        if i>=len(lines) or not lines[i].startswith('VAC_WORDS '):raise ValueError('Missing packed words')
        packed=lines[i][len('VAC_WORDS '):];i+=1;stride=(width+1)//2
        if len(packed)!=size*stride or set(packed)-set('0123456789abcdef'):raise ValueError('Invalid packed word length/alphabet')
        for word in range(size):
            bits=''
            for char in packed[word*stride:(word+1)*stride]:
                value=int(char,16);bits+=str(value&3)+str(value>>2)
            if width%2 and bits[-1]!='0':raise ValueError('Nonzero packed padding')
            result.append(f'VAR_WORD {word} '+bits[:width])
        if dense.pointer(metadata[14]):
            if i>=len(lines) or not lines[i].startswith('VAR_CACHE '):raise ValueError('Missing cached ownership')
            result.append(lines[i]);i+=1;word=0
            while word<size:
                if i>=len(lines):raise ValueError('Truncated cache runs')
                row=lines[i].split();i+=1
                if len(row)!=3 or row[0]!='VAC_CACHE_RUN':raise ValueError('Missing cache run')
                count=int(row[1]);dense.pointer(row[2])
                if count<=0 or count>size-word:raise ValueError('Invalid cache run length')
                for index in range(word,word+count):result.append(f'VAR_CACHE_WORD {index} {row[2]}')
                word+=count
    while i<len(lines) and lines[i].startswith('VAR_PORT '):result.append(lines[i]);i+=1
    if i!=len(lines)-1 or not lines[i].startswith('VAC_END '):raise ValueError('Incomplete compact inventory')
    result.append(lines[i].replace('VAC_END','VAR_END',1))
    dense.parse(result) # Structural validation permits deliberately corrupted links.
    return result


def separate(lines):
    ordinary=[];packed=[];i=0
    while i<len(lines):
        if lines[i].startswith('VAC_BEGIN '):
            start=i
            while i<len(lines) and not lines[i].startswith('VAC_END '):i+=1
            if i==len(lines):raise ValueError('Truncated compact frame')
            packed.append(lines[start:i+1])
        else:ordinary.append(lines[i])
        i+=1
    full=[];i=0
    while i<len(ordinary):
        if ordinary[i].startswith('VAR_BEGIN '):
            start=i
            while i<len(ordinary) and not ordinary[i].startswith('VAR_END '):i+=1
            if i==len(ordinary):raise ValueError('Truncated dense frame')
            full.append(ordinary[start:i+1])
        i+=1
    if len(full)!=len(packed):raise ValueError('Missing paired array image')
    for a,b in zip(full,packed):
        if a!=expand(b):raise ValueError('Compact image differs from complete dense image')
    return ordinary,len(full),sum(len(('\n'.join(f)+'\n').encode()) for f in full),sum(len(('\n'.join(f)+'\n').encode()) for f in packed)


def review(root):
    count=full_bytes=compact_bytes=0
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,full,compact=separate(p.read_text().splitlines())
            p.write_text('\n'.join(lines)+'\n' if lines else '')
            count+=n;full_bytes+=full;compact_bytes+=compact
        result=dense.review(copied)
    if not count or not 0<compact_bytes<full_bytes:raise ValueError('No complete compact savings')
    result.update(denseAndCompactExactlyEqual=True,matchedSnapshots=count,denseBytes=full_bytes,compactBytes=compact_bytes)
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/array_compact_probe.c' if ext=='c' else 'fixtures/array_compact_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    shutil.copy2(HERE/'fixtures/array_unsupported.v',out/'unsupported.v')
    for family in ('auto','two','callback'):commands.append(['iverilog','-g2012','-DARRAY_'+family.upper(),'-o',str(out/(family+'.vvp')),str(out/'unsupported.v')])
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ARRAY_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
        for family in ('auto','two','callback'):
            command=cmd[:-1]+[family+'.vvp'];r=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            label=family+'-'+name
            (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
            runs[label]=dict(command=command,exitCode=r.returncode,library=str(lib),mode=mode)

    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('array_compact_probe.py','array_probe.py','array_source_contract.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/array_compact_probe.c','fixtures/array_compact_probe.v','fixtures/array_unsupported.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Lossless compact array snapshots and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
