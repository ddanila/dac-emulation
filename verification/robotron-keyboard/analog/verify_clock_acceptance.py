#!/usr/bin/env python3
"""Recompute CPU-clock screens from the complete retained startup captures."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

from clock_voltage import inspect as voltage
from clock_timing import inspect as timing

HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('report',type=Path)
    a=ap.parse_args()
    report=json.loads((a.report/'assessment.json').read_text())
    receipt=json.loads((a.report/'retention.json').read_text())
    assert sha(a.report/'assessment.json')==receipt['assessmentSha256']
    assert sha(a.report/'captures.tar.xz')==receipt['sha256']
    for name,digest in report['sources'].items():
        assert sha(HERE/name)==digest,name
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(a.report/'captures.tar.xz') as archive:
        expected={'assessment.json':receipt['assessmentSha256']}
        for row in report['cases']:
            expected.update({row['id']+'/'+name:digest for name,digest in row['artifacts'].items()})
        members=archive.getmembers()
        assert len(members)==len(expected) and {m.name for m in members}==set(expected)
        for member in members:
            assert member.isfile()
            payload=archive.extractfile(member).read()
            assert hashlib.sha256(payload).hexdigest()==expected[member.name],member.name
            if Path(member.name).name in ('clock.txt','supply.txt'):
                target=Path(tmp)/member.name
                assert target.resolve().is_relative_to(Path(tmp).resolve())
                target.parent.mkdir(exist_ok=True);target.write_bytes(payload)
        for row in report['cases']:
            if not row['completed']:
                assert row['passed'] is False and row.get('error');continue
            folder=Path(tmp)/row['id']
            v=voltage(folder/'clock.txt',folder/'supply.txt',diagnostic_columns=2)
            for key in ('supplyEpochs','resetBoundary'):v.pop(key,None)
            t=timing(folder/'clock.txt',folder/'supply.txt',row['maximumStepNs'],diagnostic_columns=2)
            assert json.loads(json.dumps(v))==row['voltage'] and json.loads(json.dumps(t))==row['timing'],row['id']
            passed=bool(v['cycles']['assessedWithinSupplyRange'] and not v['cycles']['missingHighExcursion'] and not v['cycles']['missingLowExcursion'] and not v['inputRangeViolations'] and t['passed'])
            assert passed==row['passed'],row['id']
    assert report['gates']['allReferenceScreensPassed']==all(r['passed'] for r in report['cases'])
    assert report['qualified'] is False
    print('Retained startup captures and CPU-clock screens reproduced; electrical qualification remains open.')

if __name__=='__main__':main()
