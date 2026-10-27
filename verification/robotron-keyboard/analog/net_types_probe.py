#!/usr/bin/env python3
"""Bind native functor/filter class names to complete graph observations."""
import argparse,collections,json,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
import net_probe as dense
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def class_name(name):
    if name=='-':return None
    match=re.fullmatch(r'(\d+)([A-Za-z_]\w*)',name)
    if not match or int(match[1])!=len(match[2]):raise ValueError('Unaudited RTTI spelling')
    return match[2]


def parse(lines):
    a=lines[0].split()
    if len(a)!=4 or a[:2]!=['VNT_BEGIN','1']:raise ValueError('Invalid native type header')
    tick,count=map(int,a[2:]);nodes=[]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=7 or a[0]!='VNT_NODE':raise ValueError('Invalid type row')
        n=dict(id=int(a[1]),key=dense.pointer(a[2]),fun=dense.pointer(a[3]),funClass=class_name(a[4]),filter=dense.pointer(a[5]),filterClass=class_name(a[6]))
        if n['id']!=len(nodes)+1 or not n['key'] or bool(n['fun'])!=bool(n['funClass']) or bool(n['filter'])!=bool(n['filterClass']):raise ValueError('Invalid class binding')
        nodes.append(n)
    if tick<0 or count<=0 or len(nodes)!=count or len({n['key'] for n in nodes})!=count or lines[-1]!=f'VNT_END {count}':raise ValueError('Incomplete class inventory')
    return dict(tick=tick,nodes=nodes)


def bind(graph,types):
    if graph['tick']!=types['tick'] or len(graph['nodes'])!=len(types['nodes']):raise ValueError('Class/graph scope mismatch')
    for g,t in zip(graph['nodes'],types['nodes']):
        if any(g[k]!=t[k] for k in ('id','key','fun','filter')):raise ValueError('Class binding differs from graph')
        if g['force']!=int(t['funClass']=='vvp_fun_force'):raise ValueError('Wrong force-helper class')
    return {kind:dict(sorted(collections.Counter(n[kind+'Class'] for n in types['nodes'] if n[kind]).items())) for kind in ('fun','filter')}


def separate(lines):
    output=[];types=[];i=0
    while i<len(lines):
        if lines[i].startswith('VNT_BEGIN '):
            start=i
            while i<len(lines) and not lines[i].startswith('VNT_END '):i+=1
            if i==len(lines):raise ValueError('Truncated class inventory')
            types.append(parse(lines[start:i+1]))
        else:output.append(lines[i])
        i+=1
    graphs=[];i=0
    while i<len(output):
        if output[i].startswith('VNG_BEGIN '):
            start=i
            while i<len(output) and not output[i].startswith('VNG_END '):i+=1
            if i==len(output):raise ValueError('Truncated graph')
            graphs.append(dense.parse(output[start:i+1]))
        i+=1
    if len(graphs)!=len(types):raise ValueError('Missing paired class inventory')
    known={};classes=set()
    for graph,typed in zip(graphs,types):
        bind(graph,typed)
        for n in typed['nodes']:
            for kind in ('fun','filter'):
                if not n[kind]:continue
                pointer=n[kind];name=n[kind+'Class'];classes.add(name)
                if pointer in known and known[pointer]!=name:raise ValueError('Live native object changed class')
                known[pointer]=name
    return output,len(graphs),classes


def review(root):
    count=0;classes=set()
    with tempfile.TemporaryDirectory() as folder:
        copied=Path(folder)
        for p in root.iterdir():
            if p.is_file():shutil.copy2(p,copied/p.name)
        for p in copied.glob('*.stdout'):
            lines,n,observed=separate(p.read_text().splitlines());count+=n;classes|=observed
            p.write_text('\n'.join(lines)+'\n' if lines else '')
        result=dense.review(copied)
    if not count or 'vvp_fun_force' not in classes:raise ValueError('Missing native class coverage')
    result.update(nativeClassBindingsMatchGraph=True,matchedTypeSnapshots=count,observedClasses=sorted(classes))
    result['notEstablished']=['Native payload contents and initialization semantics','Operational board class inventory and capture budgets','General rollback']
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed native build')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/net_types_probe.c' if ext=='c' else 'fixtures/net_probe.v'),out/('probe.'+ext))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled','corrupt'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_NET_PROBE='off' if mode in ('baseline','disabled') else 'on' if mode=='enabled' else 'corrupt');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Native runtime changed')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('net_types_probe.py','net_probe.py','fixtures/net_types_probe.c','fixtures/net_probe.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed graph assessment')
        print('Native class bindings and graph controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need native runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
