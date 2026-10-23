#!/usr/bin/env python3
"""Retain bounded repeat attempts and complete short-window numerical evidence."""
import argparse,hashlib,json,lzma,re,tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def retain(build,out):
    out.mkdir(parents=True,exist_ok=False)
    files={}
    for name in ['direct-repeat-prepared','direct-repeat-disabled','direct-repeat-adc-only',
                 'direct-repeat-25','direct-repeat-12.5','direct-repeat-6.25','direct-repeat-startup']:
        for path in sorted((build/name).rglob('*')):
            if path.is_file() and path.suffix in ('.json','.cir','.log','.txt','.v','.c','.h','.vvp'):
                files[str(path.relative_to(build))]=path
    for level in ('25','12.5','6.25'):
        for name in ('bus-trace.txt','wr-trace.txt','driver-trace.txt'):
            path=build/('7406-live-'+level)/name
            files['short-extra/'+level+'/'+name]=path
    hashes={name:{'sha256':sha(path),'bytes':path.stat().st_size} for name,path in files.items()}
    with lzma.open(out/'captures.tar.xz','wb',preset=3) as compressed,tarfile.open(fileobj=compressed,mode='w|') as archive:
        for name,path in files.items():
            info=tarfile.TarInfo(name);info.size=path.stat().st_size;info.mode=0o644
            with path.open('rb') as stream:archive.addfile(info,stream)
    report={'completed':False,'numericallyQualified':False,'electricallyQualified':False,
        'requiredRepeatEndSeconds':1.601,'scope':'Pragmatic bounded investigation: full endpoints were requested, but the full repeat campaign is incomplete. No timeout or failed control is a pass.',
        'shortWindow':json.loads((build/'direct-repeat-short-all-saved.json').read_text()),
        'startupDiagnostic':json.loads((build/'direct-repeat-startup/assessment.json').read_text()),'repeatAttempts':{},
        'preflight':json.loads((build/'direct-repeat-prepared/preflight.json').read_text()),
        'sources':{name:sha(HERE/name) for name in ['live_transition_probe.py','network_refinement_review.py','complete_network_review.py','saved_network_review.py','numerical_voltage_budget.py','startup_drive_review.py','retain_direct_repeat.py']}}
    for name in ('disabled','adc-only','25','12.5','6.25'):
        directory=build/('direct-repeat-'+name);r=json.loads((directory/'run.json').read_text());log=(directory/'ngspice.log').read_text()
        progress=re.findall(r'Reference value\s*:\s*([0-9.eE+-]+)',log)
        failures=re.findall(r'^.*(?:Timestep too small|simulation\(s\) aborted).*$',log,re.M)
        report['repeatAttempts'][name]={'timedOut':r['timedOut'],'elapsedSeconds':r['elapsedSeconds'],
            'exitCode':r['exitCode'],'solverDiagnostic':r['solverDiagnostic'],'solverFailures':failures,
            'lastProgressSeconds':float(progress[-1]) if progress else None,
            'progressBoundary':'Console progress only; not a retained waveform endpoint or completion evidence.',
            'passed':False}
    finest=json.loads((build/'direct-repeat-6.25/run.json').read_text())
    vectors=len(finest['observationSignals'])+1
    report['resourceEstimate']={'minimumFinestVectorBytes':int(1.601/(6.25e-9))*vectors*8,
        'basis':'Lower bound from maximum step and saved double vectors, before adaptive steps, solver state and text exports. Not an observed allocation or runtime forecast.'}
    report['decision']='Use the functional digital release for full keyboard traffic. Short board-node voltage differences meet 10 mV; retain the stricter all-saved failure. Keep DAC-corner correction opt-in based on the bounded startup control. Resume full analog repeat only when it informs a concrete model or receiver decision and capture/runtime costs are addressed.'
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    archive_sha=sha(out/'captures.tar.xz');parts=[]
    with (out/'captures.tar.xz').open('rb') as stream:
        for index,chunk in enumerate(iter(lambda:stream.read(40*1024*1024),b'')):
            part=out/f'captures.tar.xz.part-{index:03d}';part.write_bytes(chunk)
            parts.append({'file':part.name,'sha256':sha(part),'bytes':len(chunk)})
    (out/'captures.tar.xz').unlink()
    (out/'retention.json').write_text(json.dumps({'archiveSha256':archive_sha,'parts':parts,'files':hashes,
        'shortSharedEvidence':'../7406-dynamic/live/{25,12.5,6.25}: decks, run receipts, network traces, receiver traces and logs are reused without changes.',
        'rom':'External standard S600; no extra ROM copy retained. The prepared input receipt pins its hash.'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);p.add_argument('out',type=Path);a=p.parse_args();retain(a.build,a.out)
