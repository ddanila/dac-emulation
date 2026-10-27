#!/usr/bin/env python3
"""Reconstruct full callback-owner images from native immutable-reference differences."""
import argparse,importlib,json,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
from callback_list_probe import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CASES={'lists':('callback_list_probe','callback_lists','c','result'),'registration':('callback_registration','callback_registration','c','r'),'nested':('callback_nested','callback_nested','c','r'),'words':('callback_word_probe','callback_words','cc','result'),'shared':('callback_word_shared','callback_words','cc','result')}


def image(tick,rows):
    lines=[f'VCL_BEGIN 1 {tick}'];callbacks=words=0
    for identity,row in sorted(rows.items()):
        part=row.splitlines()
        if not row.endswith('\n') or not part or not part[0].startswith(f'VCL_OWNER {identity} '):raise ValueError('Wrong compact owner identity')
        if any(not line.startswith(('VCL_CALLBACK ','VCL_WORD ')) for line in part[1:]):raise ValueError('Unexpected owner payload')
        callbacks+=sum(line.startswith('VCL_CALLBACK ') for line in part);words+=sum(line.startswith('VCL_WORD ') for line in part);lines.extend(part)
    lines.append(f'VCL_END {len(rows)} {callbacks} {words}');parse(lines);return lines


def block(lines,start=0):
    a=lines[start].split()
    if len(a)!=6 or a[0]!='VLD_BEGIN' or a[1] not in ('R','D'):raise ValueError('Invalid compact callback header')
    mode=a[1];tick,total,count,drops=map(int,a[2:]);rows={};removed=[];i=start+1
    if min(tick,total,count,drops)<0 or count>total:raise ValueError('Invalid compact dimensions')
    for _ in range(count):
        if i>=len(lines):raise ValueError('Missing compact callback row')
        a=lines[i].split();i+=1
        if len(a)!=5 or a[0]!='VLD_ROW':raise ValueError('Invalid compact callback row')
        identity,prefix,suffix=map(int,a[1:4])
        if identity<=0 or min(prefix,suffix)<0 or rows and identity<=max(rows):raise ValueError('Invalid owner identity/splice')
        if a[4]!='-' and not re.fullmatch(r'(?:[0-9a-f]{2})+',a[4]):raise ValueError('Invalid compact bytes')
        data='' if a[4]=='-' else bytes.fromhex(a[4]).decode('ascii')
        if mode=='R':
            if prefix or suffix:raise ValueError('Reference depends on prior state')
            rows[identity]=data
        else:rows[identity]=(prefix,suffix,data)
    for _ in range(drops):
        if i>=len(lines):raise ValueError('Missing owner removal')
        a=lines[i].split();i+=1
        if len(a)!=2 or a[0]!='VLD_DROP':raise ValueError('Invalid owner removal')
        identity=int(a[1])
        if identity<=0 or identity in rows or removed and identity<=removed[-1]:raise ValueError('Aliased or reordered owner removal')
        removed.append(identity)
    if i>=len(lines) or lines[i]!=f'VLD_END {count} {drops}':raise ValueError('Invalid compact footer')
    if mode=='R':
        if drops or count!=total:raise ValueError('Incomplete reference')
        image(tick,rows)
    return dict(mode=mode,tick=tick,total=total,rows=rows,removed=removed),i+1


def reconstruct(reference,frame):
    if frame['mode']!='D':raise ValueError('Expected compact difference')
    rows=dict(reference)
    for identity in frame['removed']:
        if identity not in reference:raise ValueError('Removal outside reference')
        del rows[identity]
    for identity,(prefix,suffix,data) in frame['rows'].items():
        old=reference.get(identity,'')
        if prefix+suffix>len(old):raise ValueError('Splice outside reference')
        row=old[:prefix]+data+(old[len(old)-suffix:] if suffix else '')
        if row==old:raise ValueError('Redundant compact row')
        rows[identity]=row
    if len(rows)!=frame['total']:raise ValueError('Incomplete owner lifecycle frame')
    return image(frame['tick'],rows)


def separate(lines):
    output=[];frames=[];reference=None;initial=refusals=reference_bytes=0;i=0
    while i<len(lines):
        if lines[i]=='VLD_REFUSED_EMPTY':refusals+=1;i+=1;continue
        if lines[i]=='VLD_INIT_GUARDS':initial+=1;i+=1;continue
        if lines[i].startswith('VLD_BEGIN '):
            f,end=block(lines,i);size=len(('\n'.join(lines[i:end])+'\n').encode());i=end
            if f['mode']=='R':
                if reference is not None or frames:raise ValueError('Reference reset')
                reference=f['rows'];reference_bytes=size
            else:
                if reference is None:raise ValueError('Difference before reference')
                frames.append((reconstruct(reference,f),size))
        else:output.append(lines[i]);i+=1
    dense=[];i=0
    while i<len(output):
        if output[i].startswith('VCL_BEGIN '):
            start=i
            while i<len(output) and not output[i].startswith('VCL_END '):i+=1
            if i==len(output):raise ValueError('Missing dense callback footer')
            dense.append(output[start:i+1])
        i+=1
    if len(dense)!=len(frames) or initial!=int(reference is not None):raise ValueError('Missing dense/compact pair or initialization guards')
    for a,(b,_) in zip(dense,frames):
        if a!=b:raise ValueError('Compact reconstruction differs from dense native image')
    return output,dict(images=len(frames),denseBytes=sum(len(('\n'.join(x)+'\n').encode()) for x in dense),deltaBytes=sum(n for _,n in frames),referenceBytes=reference_bytes,refusals=refusals)


def review_case(root,case):
    totals=dict(images=0,denseBytes=0,deltaBytes=0,referenceBytes=0,refusals=0)
    with tempfile.TemporaryDirectory() as tmp:
        copy=Path(tmp);shutil.copy2(root/'run.json',copy/'run.json')
        modes=json.loads((root/'run.json').read_text())['runs']
        for mode in modes:
            lines,stats=separate((root/(mode+'.stdout')).read_text().splitlines())
            expected_refusals=sum(line.startswith(('LST_UNADMITTED_REFUSED','LST_ACTIVE_REFUSED','REG_ACTIVE_REFUSED','REG_ACTIVE_AFTER_ADD_REFUSED','REG_NEW_REFUSED','REG_UNADMITTED_REFUSED','NEST_REFUSED')) or line.startswith(('LST_FAULT ','WORD_FAULT ')) and line.endswith(' -1') for line in lines)
            if stats['refusals']!=expected_refusals:raise ValueError('Missing compact refusal paired with dense refusal')
            for k,v in stats.items():totals[k]+=v
            (copy/(mode+'.stdout')).write_text('\n'.join(lines)+'\n');shutil.copy2(root/(mode+'.stderr'),copy/(mode+'.stderr'))
        if case=='shared':
            for name in ('compiler.vvp','probe.vvp','adapter.json'):shutil.copy2(root/name,copy/name)
        result=importlib.import_module(CASES[case][0]).review(copy)
    if not totals['images'] or not totals['referenceBytes']:raise ValueError('Missing compact native evidence')
    return dict(denseControls=result,compact=totals)


def review(root):
    return dict(qualified=False,controlsPassed=True,cases={case:review_case(root/case,case) for case in CASES},scope='Every successful native snapshot is paired with exact compact reconstruction against an immutable owner reference. Dense reviewers independently validate cancellation, growth, nested refusal and array-word faults/continuation. Full native admission preflight runs before compact output; initialization guards and refusal paths remain explicit.',notEstablished=['Native owner allocation/removal and unsupported-family controls through compact APIs','Actual board compact cost and combined operational integration','Deep typed referents, suspended traversal and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed compact runtime')
    for case,(module,fixture,ext,param) in CASES.items():
        folder=out/case;folder.mkdir();source=(HERE/f'fixtures/{fixture}.{ext}').read_text()
        start=source.index('static char* snapshot(');end=source.index('return p;',start)
        source=source[:end]+f'compact_check(*{param});'+source[end:]
        (folder/f'probe.{ext}').write_text('#include "compact.h"\n'+source)
        shutil.copy2(HERE/'fixtures/callback_delta_adapter.h',folder/'compact.h');shutil.copy2(HERE/f'fixtures/{fixture}.v',folder/'probe.v')
        flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
        commands=[['iverilog','-g2012','-o',str(folder/'probe.vvp'),str(folder/'probe.v')],['c++' if ext=='cc' else 'cc',*(['-std=c++11'] if ext=='cc' else []),*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(folder/'probe.vpi'),str(folder/f'probe.{ext}')]]
        for cmd in commands:subprocess.run(cmd,check=True)
        if case=='shared':importlib.import_module(module).adapt(folder/'probe.vvp')
        pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',folder/'probe.vpi',folder/'probe.vvp',*modules.glob('*.vpi')]};runs={}
        for mode in ('baseline','disabled','enabled',*(['corrupt'] if case in ('lists','words','shared') else [])):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so';flag='off' if mode in ('baseline','disabled') else ('corrupt' if mode=='corrupt' else 'on')
            env=dict(os.environ,K7658_CALLBACK_LISTS=flag,K7658_CALLBACK_WORDS=flag);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=folder,env=env,capture_output=True,text=True,timeout=30)
            (folder/(mode+'.stdout')).write_text(r.stdout);(folder/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib),mode=flag);r.check_returncode()
        if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during compact controls')
        (folder/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('callback_delta.py','fixtures/callback_delta_adapter.h',f'fixtures/{fixture}.{ext}',f'fixtures/{fixture}.v',module+'.py')}),indent=2)+'\n')
    shutil.copy2(candidate/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed compact assessment')
        print('Compact callback lists reconstruct dense native controls exactly.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
