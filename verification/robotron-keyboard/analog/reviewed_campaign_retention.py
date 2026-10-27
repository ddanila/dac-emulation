"""Retain fully reviewed campaigns separately from initialized budget evidence."""
import json,shutil
from pathlib import Path
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def destination(reports,stage):
    if stage not in ('wire','signal','mux'):raise ValueError('Unsupported reviewed campaign stage')
    result=Path(reports)/(stage+'-board-reviewed')
    if result.exists():raise ValueError('Reviewed campaign destination already exists: '+str(result))
    return result


def files(root):
    return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def retain(source,assessment,producer,out,sources):
    source,assessment,producer,out=map(Path,(source,assessment,producer,out))
    if out.exists():raise ValueError('Reviewed campaign destination already exists')
    if any((source/name).exists() for name in ('manifest.json','assessment.json','producer.py','retention.json')):raise ValueError('Capture tree already contains retention metadata')
    result=json.loads(assessment.read_text())
    if any(result.get(k) is not True for k in ('controlsPassed','reviewCompleted','firmwareRecordsExactlyEqual')):raise ValueError('Need a complete passing campaign review')
    if not result.get('receipts') or not sources:raise ValueError('Missing reviewed receipts or source identities')
    for mode,digest in result['receipts'].items():
        if Path(mode).name!=mode or mode in ('.','..') or sha(source/mode/'run.json')!=digest:raise ValueError('Changed reviewed capture receipt')
    for name,digest in sources.items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or sha(HERE/path)!=digest:raise ValueError('Changed reviewed source')
    before=files(source);assessment_sha=sha(assessment);producer_sha=sha(producer)
    shutil.copytree(source,out)
    if files(out)!=before or files(source)!=before:raise ValueError('Retained campaign files differ')
    shutil.copy2(assessment,out/'assessment.json');shutil.copy2(producer,out/'producer.py')
    if sha(out/'assessment.json')!=assessment_sha or sha(assessment)!=assessment_sha or sha(out/'producer.py')!=producer_sha or sha(producer)!=producer_sha:raise ValueError('Changed assessment or producer during retention')
    (out/'retention.json').write_text(json.dumps(dict(qualified=False,exactRetainedFileIdentity=True,reviewedAssessmentSha256=assessment_sha,scope='Exact copy of the fully reviewed bounded capture. Retention verifies file identity, not a second semantic replay.'),indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps(dict(files=files(out),sources=sources),indent=2)+'\n')
    check(out)
