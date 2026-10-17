#!/usr/bin/env python3
"""Revalidate a completed boot after correcting the old idle-transmit assertion."""
import argparse
import hashlib
import json
from pathlib import Path

from boot_cosim import validate, sha

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    args=p.parse_args();out=args.directory.resolve()
    original=json.loads((out/'report.json').read_text())
    if original.get('preparedOnly') or (not original.get('passed') and original.get('error') !=
            'Boot did not exercise instruction fetch and keyboard I/O'):
        raise ValueError('Only completed successful runs or the known idle-transmit assertion can be rechecked')
    inputs=json.loads((out/'run-inputs.json').read_text())
    if sha(out/'boot.cir')!=inputs['deckSha256'] or inputs['deckSha256']!=original['deckSha256']:
        raise ValueError('Original deck provenance differs')
    rom=bytes(int(word,16) for word in (out/'s600.hex').read_text().split())
    if hashlib.sha256(rom).hexdigest()!=inputs['romSha256']:
        raise ValueError('Original ROM input differs')
    # Preserve original execution/assumption evidence and its failed report.
    report=dict(original)
    report.pop('error',None)
    report['passed']=False
    report['revalidation']={'reason':'Idle S600 scanning need not transmit without a key stimulus',
                            'originalReportSha256':sha(out/'report.json'),
                            'validatorSha256':sha(HERE/'boot_cosim.py'),
                            'recheckSha256':sha(Path(__file__)),
                            'logSha256':sha(out/'ngspice.log'),
                            'traceSha256':sha(out/'trace.txt')}
    try:
        validate(out,report)
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:(out/'revalidation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'revalidation.json')


if __name__=='__main__':main()
