#!/usr/bin/env python3
"""Live RC differential control for replayable streaming retention."""
import argparse
import json
from pathlib import Path
import shutil

from retained_stream_refinement import capture
from stream_refinement_capture import capture as unretained
from retained_stream_review import replay
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('retained_stream_control.py','retained_stream_capture.py','retained_stream_review.py',
         'retained_stream_refinement.py','stream_capture.py','stream_refinement_capture.py',
         'raw_stream_review.py','raw_waveform.py','host_waveform_comparison.py',
         'filter_truncation_log.py','ngspice_runtime.py')


def run(out):
    prior=HERE/'reports/live-stream-transport'
    old=json.loads((prior/'assessment.json').read_text())
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    decks=[]
    for i in range(3):
        name=f'source-level{i}.cir';path=out/name
        shutil.copyfile(prior/name,path);decks.append(path)
    runtime=old['runtime']
    args=(Path(runtime['executable']['path']),Path(runtime['spinit']['path']),60,[],{})
    baseline=unretained(decks,out/'unretained',*args)
    retained=capture(decks,out/'retained',*args,storage_limits=dict(max_raw_bytes=1024**2,
        max_compressed_raw_bytes=256*1024,max_log_bytes=1024**2,
        max_compressed_log_bytes=256*1024,max_log_line_bytes=8192))
    reviewed=replay(out/'retained')
    if baseline['transport']['comparisons']!=retained['transport']['comparisons']:
        raise ValueError('Retention changed live comparisons')
    if baseline['voltageGatePassed']!=retained['voltageGatePassed']:
        raise ValueError('Retention changed numerical gate')
    if reviewed['comparisons']!=retained['transport']['comparisons']:
        raise ValueError('Stored replay differs from live comparison')
    result=dict(completed=True,qualified=False,comparisonExactlyPreserved=True,
        replayExactlyPreserved=True,voltageGatePassed=retained['voltageGatePassed'],
        storageUsage=reviewed['storageUsage'],
        scope='Complete three-level live RC control, matched unretained transport and full archived-sample replay. Does not establish keyboard-scale runtime/memory or full-repeat qualification.',
        sources={n:sha(HERE/n) for n in SOURCES})
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps(dict(files={str(p.relative_to(out)):sha(p)
        for p in sorted(out.rglob('*')) if p.is_file()},sources=result['sources']),indent=2)+'\n')
    return result


def check(out):
    manifest=json.loads((out/'manifest.json').read_text())
    if manifest['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Changed sources')
    actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}
    if actual!=manifest['files']:raise ValueError('Changed retained control')
    result=replay(out/'retained')
    retained=json.loads((out/'retained/assessment.json').read_text())
    baseline=json.loads((out/'unretained/assessment.json').read_text())
    report=json.loads((out/'assessment.json').read_text())
    if result['comparisons']!=baseline['transport']['comparisons'] or result['comparisons']!=retained['transport']['comparisons']:
        raise ValueError('Changed comparison')
    if not report['completed'] or report['qualified'] or report['storageUsage']!=result['storageUsage']:
        raise ValueError('Changed control result')
    print('Live retained transport and every-sample replay verified.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true')
    a=p.parse_args()
    if a.check:check(a.out)
    else:print(json.dumps(run(a.out),indent=2))
