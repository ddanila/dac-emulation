#!/usr/bin/env python3
"""Exercise alias/net/real/string rejection in dense and compact native observers."""
import argparse,json,os,platform,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FAMILIES=('alias','net','real','string')


def alias_program(text):
    matches=list(re.finditer(r'^(\S+) \.array "memory",[^\n]+;$',text,re.M))
    if len(matches)!=1 or 'family_alias' in text:raise ValueError('Ambiguous alias source')
    match=matches[0]
    return text[:match.end()]+'\nfamily_alias .array "other", '+match[1]+';'+text[match.end():]


def review(root):
    receipt=json.loads((root/'run.json').read_text())
    for family in FAMILIES:
        compiled=(root/(family+'.vvp')).read_text()
        patterns={'net':r'\.array "other", -?\d+ -?\d+;', 'real':r'\.array/real "other",', 'string':r'\.array/str "other",'}
        if family=='alias':
            if compiled!=alias_program((root/'alias-original.vvp').read_text()):raise ValueError('Changed alias injection')
        elif not re.search(patterns[family],compiled):raise ValueError('Missing unsupported family declaration')
        reference=None
        for mode in ('baseline','disabled','dense','compact'):
            name=family+'-'+mode;lines=(root/(name+'.stdout')).read_text().splitlines()
            if (root/(name+'.stderr')).read_text():raise ValueError('Unexpected family diagnostic')
            if mode in ('dense','compact'):
                if receipt['runs'][name]['exitCode']!=2 or lines!=['FAMILY_PRESENT '+family,'ARRAY_REFUSED '+mode]:raise ValueError('Unsupported storage accepted or inventory partially emitted')
            else:
                if receipt['runs'][name]['exitCode']!=0 or len(lines)!=3 or lines[:2]!=['FAMILY_PRESENT '+family,'CONTINUED 1000'] or '$finish called at 1000 (1ps)' not in lines[-1]:raise ValueError('Invalid family control')
                if reference is None:reference=lines
                elif reference!=lines:raise ValueError('Disabled observer changed continuation')
    return dict(qualified=False,controlsPassed=True,unsupportedProfilesRefused=list(FAMILIES),denseAndCompactRefuseWithoutPartialInventory=True,disabledContinuationExactlyEqual=True,
        aliasStorageSharingExercised=True,scope='Pinned native runtime; alias fixture adds the audited compiled alias declaration, verifies shared writes/readback and restores before observation. Other families are compiled from HDL. VPI setup deliberately materializes handles before observation.',
        notEstablished=['Support for these storage families or their rollback','Dynamic/class/object array controls','Full-board qualification'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed native runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/array_family.'+ext),out/('probe.'+ext))
    commands=[]
    for family in FAMILIES:
        command=['iverilog','-g2012','-DFAMILY_'+family.upper(),'-o',str(out/(family+'.vvp')),str(out/'probe.v')]
        commands.append(command);subprocess.run(command,check=True)
    p=out/'alias.vvp';shutil.copy2(p,out/'alias-original.vvp');p.write_text(alias_program(p.read_text()))
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    command=['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')];commands.append(command);subprocess.run(command,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]};runs={}
    for family in FAMILIES:
        for mode in ('baseline','disabled','dense','compact'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_ARRAY_FAMILY=family,K7658_ARRAY_MODE='off' if mode in ('baseline','disabled') else mode)
            env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'.vvp']
            r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30);name=family+'-'+mode
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib))
    if any(sha(Path(p))!=v for p,v in pins.items()):raise ValueError('Runtime changed during probe')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('array_family_probe.py','fixtures/array_family.c','fixtures/array_family.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('candidate','baseline','modules','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Unsupported array families refused by dense and compact observers.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
