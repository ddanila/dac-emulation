"""Check page-16 source DC paths and neck-stage operating points.

This is an A1 topology/function check, not a service-waveform or CRT test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import inventory_audit
import page16_neck_compare
import reference

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'profiles/k7222-11-neck.json'
MODELS=ROOT/'circuits/k7222-11-neck-models.cir'
BENCH=ROOT/'circuits/k7222-11-neck-bench.cir'
PROBES=('p41','vid','intens','clamp','base','collector','brightness','tail',
        'cathode','g1','g2','g4')
ROOT_NETS={'41P','OO','VID','IS','UG1_INPUT','UG2_INPUT','UG4_INPUT','HEATER_10_7P'}


def sha_bytes(value):return hashlib.sha256(value).hexdigest()
def sha(path):return sha_bytes(Path(path).read_bytes())


def dc_paths(source):
    terminal_net={}
    for net,terminals in source['nets'].items():
        for terminal in terminals:
            if terminal in terminal_net:raise ValueError('source terminal occurs twice')
            terminal_net[terminal]=net
    links={net:set() for net in source['nets']}
    for number in range(1,9):
        a=terminal_net[f'R{number}:1'];b=terminal_net[f'R{number}:2']
        links[a].add(b);links[b].add(a)
    for diode in source['diode_directions']:
        a=diode['anode_net'];b=diode['cathode_net']
        links[a].add(b);links[b].add(a)
    if not ROOT_NETS<=set(links):raise ValueError('missing external source net')
    reachable=set(ROOT_NETS);pending=list(ROOT_NETS)
    while pending:
        for neighbor in links[pending.pop()]:
            if neighbor not in reachable:
                reachable.add(neighbor);pending.append(neighbor)
    return dict(external_source_or_pass_through_nets=sorted(ROOT_NETS),
                reachable_nets=sorted(reachable),unreachable_nets=sorted(set(links)-reachable),
                interpretation='resistor paths plus possible diode conduction; the bench checks actual operating points')


def run(source_pdf):
    comparison=page16_neck_compare.run(source_pdf)
    if not comparison['passed']:raise ValueError('source-to-KiCad page-16 pins differ')
    comparison_path=page16_neck_compare.ROOT/'reference/k7222-11/page16-neck-comparison.json'
    if comparison!=json.loads(comparison_path.read_text()):
        raise ValueError('saved page-16 pin comparison is stale')
    source=json.loads(page16_neck_compare.SOURCE.read_text())
    paths=dc_paths(source)
    if paths['unreachable_nets']:raise ValueError('page-16 source node has no DC route')
    profile=reference.read_profile(PROFILE)
    profile['probes']=[dict(name=name,unit='V',expression=f'v({name})') for name in PROBES]
    inventory=json.loads(inventory_audit.INVENTORY.read_text())
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory)
        xml=out/'neck.xml'
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                        '-o',str(xml),str(page16_neck_compare.SHEET)],
                       check=True,capture_output=True,text=True)
        parts=reference.source_connectivity(xml,inventory,'012-6891')
        parameters=reference.parameter_values(profile,{})
        deck=reference.deck(profile,parts,parameters,0,.0004,2e-7,
                            MODELS.read_text(),BENCH.read_text())
        (out/'run.cir').write_text(deck)
        solver=subprocess.run(['ngspice','-n','-b','-o','solver.log','run.cir'],
                              cwd=out,capture_output=True,text=True)
        if solver.returncode:raise ValueError('neck bench solve failed: '+(out/'solver.log').read_text()[-1000:])
        rows=reference.read_samples(out/'samples.txt',profile['probes'],0,.0004,2e-7)
    states={}
    for name,time in (('dark_video',50e-6),('bright_video',150e-6),
                      ('intensity_only',250e-6),('video_and_intensity',350e-6)):
        row=min(rows,key=lambda item:abs(item[0]-time))
        states[name]=dict(time_s=row[0],volts=dict(zip(PROBES,row[1:])))
    dark=states['dark_video']['volts'];bright=states['bright_video']['volts']
    both=states['video_and_intensity']['volts']
    checks={
        'positive_electrolytic_rail':40<dark['p41']<42,
        'dark_transistor_off':30<dark['collector']<41 and abs(dark['base'])<.1,
        'bright_transistor_on':.5<bright['base']<1 and 0<bright['collector']<2,
        'video_moves_collector':dark['collector']-bright['collector']>30,
        'intensity_moves_cathode':both['cathode']-bright['cathode']>3,
        'grid_rails_plausible':(-30<dark['g1']<-20 and 300<dark['g2']<400
                                and 0<dark['g4']<350),
        'source_c1_polarity':source['capacitor_polarity']=={
            'part':'C1','positive_net':'41P','negative_net':'OO'},
    }
    return dict(format='dac-monitor-page16-neck-static-v1',
                qualification='source topology, DC routes and isolated neck-stage function; no manual service-waveform claim',
                source_comparison_sha256=sha(comparison_path),
                source_netlist_sha256=sha(page16_neck_compare.SOURCE),
                sheet_sha256=sha(page16_neck_compare.SHEET),
                profile_sha256=sha(PROFILE),models_sha256=sha(MODELS),bench_sha256=sha(BENCH),
                deck_sha256=sha_bytes(deck.encode()),
                source_dc_paths=paths,device_model_assumptions='bounded neck profile; no fitted original silicon curves',
                state_voltages=states,checks=checks,passed=all(checks.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.source_pdf)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('page-16 static/function checks:', 'pass' if report['passed'] else 'fail')
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
