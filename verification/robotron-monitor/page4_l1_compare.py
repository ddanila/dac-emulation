"""Compare the conditional page-4 L1 feed read with the exported output sheet."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import lab
import reference
import steady_supply

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'reference/k7222-11/page4-l1-source-read.json'
SHEET=ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
NETS={'41P':'p41','R42_TO_L1':'h_chokein','FILTER_FEED':'h_feed',
      '00':'0','FLYBACK_HOT':'h_hot'}
PINS={'R42':['1','2'],'L1':['1','2'],'C22':['1','2']}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    source=json.loads(SOURCE.read_text())
    pin_to_net={}
    for net,pins in source['selected_model_nets'].items():
        for pin in pins:
            if pin in pin_to_net:raise ValueError('source pin occurs on two nets')
            pin_to_net[pin]=NETS[net]
    expected={f'012-6921:{name}':[pin_to_net[f'{name}:{pin}'] for pin in pins]
              for name,pins in PINS.items()}
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);xml=out/'output.xml'
        lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml',
                         '-o',str(xml),str(SHEET)],out,out/'export.log')
        inventory=json.loads(INVENTORY.read_text())
        parts=reference.source_connectivity(xml,inventory,'012-6921',
                                            steady_supply.OUTPUT_CONTRACTS)
    actual={p['source_id']:p for p in parts}
    misses=[dict(source_id=sid,expected_nodes=nodes,
                 actual_nodes=actual[sid]['nodes'] if sid in actual else None)
            for sid,nodes in expected.items() if sid not in actual or actual[sid]['nodes']!=nodes]
    hot=actual['012-6921:V18']['nodes'][0]
    t3=actual['012-6921:T3']['nodes'][0]
    crossing_match=(hot==t3==pin_to_net['V18:C']==pin_to_net['T3:X2_7']
                    and hot!=actual['012-6921:L1']['nodes'][0])
    return dict(format='dac-monitor-page4-l1-comparison-v1',
        qualification='conditional local A1 source-to-KiCad pin comparison; crossing selected by circuit stress, not a settled printed dot',
        source_sha256=sha(SOURCE),source_pdf_sha256=source['source']['pdf_sha256'],
        sheet_sha256=sha(SHEET),selected_component_pins=sum(map(len,expected.values())),
        hot_line_terminals_checked=2,missing_or_changed_pins=misses,
        hot_crossing_separate_from_l1=crossing_match,
        open_checks=source['open_checks'],passed=not misses and crossing_match)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{report['selected_component_pins']} component pins checked; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
