#!/usr/bin/env python3
"""Attach a screened experimental 7406 candidate to existing electrical D0/WR.

Input is firmware_io_cosim --prepare-only --electrical-bus --electrical-wr
--serial-driver 7406-dc --bus-7406-pf 0. Pin capacitance is in the candidate.
This prepares a diagnostic run; selected device screens are not board admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from ttl7406_dynamic import model
from gate_switching_probe import sha


def checked_candidate(report, case_index):
    if not report['completed']:
        raise ValueError('Incomplete device investigation')
    case=report['cases'][case_index]
    if not case['selectedScreensPass'] or not all(c['withinLimit'] for c in case['dc']) or not all(c['converged'] and c['withinDelayScreen'] for c in case['validation']):
        raise ValueError('Candidate fails device screens')
    candidate=model(**case['parameters'])
    name=f'junction-{case["parameters"]["junction_pf"]:g}pf/candidate.cir'
    if hashlib.sha256(candidate.encode()).hexdigest()!=report['artifacts'].get(name):
        raise ValueError('Parameters differ from the tested model')
    return candidate


def transform(deck, candidate):
    for label,signal,output in [('data','n_D0','n_TA_DATEN'),('clock','n_WR_N','n_TA_TAKT')]:
        expected=f'X{label} {signal} {output} driver_vp 0 TTL7406_NOMINAL input_br=.01'
        if deck.splitlines().count(expected)!=1:
            raise ValueError('Requires physical '+label+' input')
        deck=deck.replace(expected,expected.replace('TTL7406_NOMINAL input_br=.01','TTL7406_DYNAMIC'))
    if 'Cwr_gate ' in deck or re.search(r'^C.*7406',deck,re.M):
        raise ValueError('Do not double-count the gate input capacitance')
    if 'Bwr_low n_WR_N ' not in deck or 'Bwr_high n_p5V n_WR_N ' not in deck:
        raise ValueError('Requires finite electrical WR drive')
    deck,count=re.subn(r'^\.subckt TTL7406_NOMINAL .*?^\.ends TTL7406_NOMINAL\n',lambda _:candidate,deck,flags=re.M|re.S)
    if count!=1:
        raise ValueError('Expected one original transistor model')
    old='Adrive [dsink csink led1 led0] [data_intent clock_intent led1_v led0_v] drive'
    if deck.splitlines().count(old)!=1:
        raise ValueError('Expected serial intent DAC')
    deck=deck.replace(old,'Adrive [led1 led0] [led1_v led0_v] drive')
    if any(s in deck for s in ('data_intent','clock_intent','OUTPUT_SINK_NOMINAL')):
        raise ValueError('Unexpected remaining serial intent path')
    lines=deck.splitlines()
    saves=[line[6:] for line in lines if line.startswith('.save ')]
    lines=[line for line in lines if not line.startswith('.save ')]
    lines.insert(lines.index('.control'),'.save '+' '.join(saves))
    deck='\n'.join(lines)+'\n'
    deck,count=re.subn(r'^wrdata trace.txt ', 'wrdata witness.txt ',deck,flags=re.M)
    if count!=1:
        raise ValueError('Missing receiver witness')
    return deck


def prepare(source, report_path, case_index, out):
    report=json.loads(report_path.read_text())
    candidate=checked_candidate(report,case_index)
    case=report['cases'][case_index]
    for name,digest in report['sources'].items():
        if sha(Path(__file__).with_name(name))!=digest:
            raise ValueError('Device evidence has stale source: '+name)
    for name,digest in report['artifacts'].items():
        if sha(report_path.parent/name)!=digest:
            raise ValueError('Changed device evidence: '+name)
    inputs=json.loads((source/'run-inputs.json').read_text())
    if inputs['assumptions']['bus7406Pf']!=0:
        raise ValueError('Gate capacitance fixture must be zero')
    deck=transform((source/'io.cir').read_text(),candidate)
    out.mkdir(parents=True,exist_ok=False)
    for name in ('io.vvp','s600.hex','controller_analog.v','scenario.json'):
        shutil.copyfile(source/name,out/name)
    (out/'io.cir').write_text(deck)
    receipt=dict(qualified=False,boardAdmission=False,diagnosticOnly=True,
                 deviceReportSha256=sha(report_path),parameters=case['parameters'],
                 sourceDeckSha256=sha(source/'io.cir'),deckSha256=sha(out/'io.cir'),
                 physicalInputs=['A1:3 D0','A1:1 WR_N'],serialIntentDacRemoved=True,
                 remainingBoundary='CPU data/WR drivers are linear endpoint stress fixtures, not qualified I/V models.',
                 inputs={name:sha(out/name) for name in ('io.vvp','s600.hex','controller_analog.v','scenario.json')})
    (out/'dynamic-driver.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--device-report',type=Path,required=True)
    p.add_argument('--case',type=int,default=0)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();prepare(a.prepared,a.device_report,a.case,a.out)
