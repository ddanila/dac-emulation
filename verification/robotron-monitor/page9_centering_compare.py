"""Compare the independent page-9 centring read with the exported bridge sheet."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import lab
import reference

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'reference/k7222-11/page9-centering-source-netlist.json'
SHEET=ROOT/'circuits/k7222-11-centering.kicad_sch'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
NET_NAMES={'X2':'hy2','X1':'hy1','L1_TO_R4':'centering_a',
           'R4_WIPER':'centering_w','R4_TO_R2':'centering_b',
           'R2_TO_LINKS':'centering_c','00':'0','12P':'p12'}
PIN_ORDER={'L1':['1','2'],'L2':['1','2'],
           'R4':['end_a','end_b','wiper'],'R2':['1','2']}
VALUES={'L1':'CENTERING_CHOKE','L2':'CENTERING_CHOKE',
        'R4':'CENTERING_POT','R2':'{centering_r2_ohm}'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    source=json.loads(SOURCE.read_text())
    if source['source']['page']!=9 or source['scope']['board']!='012-6931':
        raise ValueError('wrong centring source scope')
    pin_to_net={}
    for net,pins in source['nets'].items():
        for pin in pins:
            if pin in pin_to_net:raise ValueError('source pin occurs on two nets: '+pin)
            pin_to_net[pin]=NET_NAMES[net]
    for name in ('L1','L2'):
        if pin_to_net[name+':1']!=pin_to_net[name+':3'] or pin_to_net[name+':2']!=pin_to_net[name+':4']:
            raise ValueError('paired choke terminals differ in source read')
    if any(pin_to_net['E'+str(n)+':right']!=net for n,net in ((1,'0'),(2,'p12'),(3,'0'),(4,'p12'))):
        raise ValueError('source rail-link map differs from page-9 read')
    expected={f'012-6931:{name}':dict(nodes=[pin_to_net[name+':'+pin] for pin in pins],
                                      value=VALUES[name]) for name,pins in PIN_ORDER.items()}
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);xml=out/'centering.xml'
        lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml',
                         '-o',str(xml),str(SHEET)],out,out/'export.log')
        inventory=json.loads(INVENTORY.read_text())
        parts=reference.source_connectivity(xml,inventory,'012-6931',
            {'CENTERING_CHOKE':2,'CENTERING_POT':3},allow_floating=True)
    actual={part['source_id']:dict(nodes=part['nodes'],value=part['value']) for part in parts}
    misses=[dict(source_id=sid,expected=value,actual=actual.get(sid))
            for sid,value in expected.items() if actual.get(sid)!=value]
    extras=sorted(set(actual)-set(expected))
    return dict(format='dac-monitor-page9-centering-comparison-v1',
        qualification='partial A1 page-9 source-to-KiCad comparison; E-link installation and coil internals unverified',
        source_netlist_sha256=sha(SOURCE),sheet_sha256=sha(SHEET),
        source_pdf_sha256=source['source']['pdf_sha256'],
        source_components=len(expected),source_component_pins=sum(len(e['nodes']) for e in expected.values()),
        paired_choke_terminals_checked=4,rail_link_terminals_checked=4,
        missing_or_changed_pins=misses,extra_kicad_components=extras,
        open_checks=source['open_checks'],passed=not misses and not extras)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{report['source_component_pins']} source component pins checked; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
