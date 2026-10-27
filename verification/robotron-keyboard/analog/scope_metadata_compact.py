#!/usr/bin/env python3
"""Replay exact native scope metadata image reuse against complete dense scans."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
import scope_metadata
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
HERE=Path(__file__).resolve().parent


class Decoder:
    def __init__(self,reference=False):
        self.tag='VSMRD' if reference else 'VSMD';self.dense='VSMR' if reference else 'VSM'
        self.parser=reference_parse if reference else metadata_parse
        self.sequence=0;self.body=None;self.full=0;self.reused=0
    def decode(self,lines):
        if len(lines)<2:raise ValueError('Truncated compact metadata')
        a=lines[0].split()
        if len(a)!=6 or a[:2]!=[self.tag+'_BEGIN','1'] or lines[-1]!=self.tag+'_END':raise ValueError('Invalid compact envelope')
        try:tick,sequence,full,size=map(int,a[2:])
        except ValueError:raise ValueError('Invalid compact fields')
        if not 0<=tick<(1<<64) or sequence!=self.sequence+1 or sequence>=(1<<64) or full not in (0,1) or size<=0:raise ValueError('Invalid compact sequence or size')
        if full:
            body='\n'.join(lines[1:-1])+'\n'
        else:
            if self.body is None or len(lines)!=2:raise ValueError('Reuse before complete reference or extra payload')
            body=self.body
        if len(body.encode('ascii'))!=size:raise ValueError('Compact body length mismatch')
        dense=f'{self.dense}_BEGIN 1 {tick}\n'+body
        self.parser(dense.splitlines())
        # Only a fully validated record can advance the decoder state.
        self.body=body;self.sequence=sequence;self.full+=full;self.reused+=1-full
        return dense


def strip(text):
    lines=text.splitlines();filtered=[];i=0;ordinal=0;refused=0
    metadata=Decoder();reference=Decoder(True);dense_bytes=compact_bytes=0
    while i<len(lines):
        line=lines[i];i+=1
        if line=='ENCODING_REFUSED':refused+=1;continue
        if not line.startswith('ENCODING_BEGIN '):filtered.append(line);continue
        ordinal+=1
        if line!=f'ENCODING_BEGIN {ordinal}':raise ValueError('Changed encoding record order')
        sections=[]
        for tag,end in (('VSM','VSM_END '),('VSMD','VSMD_END'),('VSMR','VSMR_END '),('VSMRD','VSMRD_END')):
            start=i
            if i>=len(lines) or not lines[i].startswith(tag+'_BEGIN '):raise ValueError('Missing encoding section')
            i+=1
            while i<len(lines) and not (lines[i].startswith(end) if end.endswith(' ') else lines[i]==end):i+=1
            if i==len(lines):raise ValueError('Truncated encoding section')
            i+=1;sections.append(lines[start:i])
        if i==len(lines) or lines[i]!='ENCODING_END':raise ValueError('Missing encoding end')
        i+=1
        for decoder,dense,compact in ((metadata,sections[0],sections[1]),(reference,sections[2],sections[3])):
            expected='\n'.join(dense)+'\n'
            if decoder.decode(compact)!=expected:raise ValueError('Reconstruction differs from complete native scan')
            dense_bytes+=len(expected.encode());compact_bytes+=len(('\n'.join(compact)+'\n').encode())
    return '\n'.join(filtered)+'\n',dict(images=ordinal,zeroOutputRefusals=refused,
        metadataFull=metadata.full,metadataReused=metadata.reused,referenceFull=reference.full,referenceReused=reference.reused,
        denseBytes=dense_bytes,compactBytes=compact_bytes)


def review(root):
    results={}
    with tempfile.TemporaryDirectory() as tmp:
        filtered=Path(tmp);shutil.copy2(root/'run.json',filtered/'run.json')
        for prefix in ('','unsupported-'):
            for mode in ('baseline','disabled','enabled'):
                name=prefix+mode;text,counts=strip((root/(name+'.stdout')).read_text())
                (filtered/(name+'.stdout')).write_text(text);shutil.copy2(root/(name+'.stderr'),filtered/(name+'.stderr'))
                if mode!='enabled' and any(counts.values()):raise ValueError('Unrequested observer execution')
                if mode=='enabled':results[name]=counts
        original=scope_metadata.review(filtered)
    normal=results['enabled'];unsupported=results['unsupported-enabled']
    if normal['zeroOutputRefusals']!=16 or any(normal[k]<=0 for k in ('images','metadataFull','metadataReused','referenceFull','referenceReused')):raise ValueError('Missing compact controls')
    if unsupported['zeroOutputRefusals']!=1 or unsupported['images']:raise ValueError('Missing initial automatic refusal')
    return dict(qualified=False,controlsPassed=True,denseReconstructionExactlyEqual=True,nativeControls=original,encoding=results,
        scope='Complete native dense scans compared byte-for-byte with compact reconstruction through fourteen mutations per round, restoration, tick changes and early/late zero-output refusals. Exact previous-body equality only; changed bodies emit in full. No operational storage, state-growth or scan-cost qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_metadata_compact.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    shutil.copy2(HERE/'fixtures/scope_metadata_compact_unsupported.v',out/'unsupported.v')
    commands.append(['iverilog','-g2012','-o',str(out/'unsupported.vvp'),str(out/'unsupported.v')])
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',out/'unsupported.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SCOPE_METADATA_COMPACT='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
        key='unsupported-'+mode;cmd=cmd[:-1]+['unsupported.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(key+'.stdout')).write_text(r.stdout);(out/(key+'.stderr')).write_text(r.stderr)
        runs[key]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
