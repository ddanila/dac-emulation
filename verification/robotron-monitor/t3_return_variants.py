"""Compare tied and open X1:3/X2:3 T3 returns under an isolated EHT load."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import t3_flyback_sign
import transformer_candidates

ROOT=Path(__file__).resolve().parent
GRAPH=ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
PARAMETERS=ROOT/'reference/k7222-11/t3-initial-parameters.json'
SIGN=ROOT/'reference/k7222-11/t3-flyback-sign-filter.json'
READ=ROOT/'reference/k7222-11/t3-drive-polarity-source-read.json'
SHEET=ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'
TRANSCRIPTION=ROOT/'reference/k7222-11/horizontal-output-transcription.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulate(graph,parameters,candidate,joined,backend):
    model,metadata=transformer_candidates.compile_model(graph,candidate,parameters,
                                                          backend=backend)
    port_nodes={'X2_7':'hot','X2_4':'0','X2_5':'0','X2_3':'upper2',
                'X1_3':'upper2' if joined else 'upper_return',
                'X1_7':'hvcold','X1_16':'hvcold','X1_1':'hvac'}
    nodes=[port_nodes.get(port,port) for port in metadata['ports']]
    shunts=[f'Rref{index} {node} 0 1G' for index,node in enumerate(nodes)
            if node not in ('hot','0')]
    with tempfile.TemporaryDirectory() as directory:
        deck=Path(directory)/'return.cir'
        deck.write_text('\n'.join([
            'T3 conditional return comparison; not a loaded monitor',model,
            '.model DHV D(IS=1n N=2 RS=100 CJO=1p TT=100n BV=15k IBV=2u)',
            'Vdrive hot 0 PULSE(0 1 20n 10n 10n 16u 62.5u)',*shunts,
            'Xtest '+' '.join(nodes)+' T3_CANDIDATE',
            'Dhv hvac eht DHV','Ctube eht 0 1n','Rhv eht 0 200Meg',
            '.control','tran 50n 312.5u',
            'meas tran emax MAX v(eht) FROM=250u TO=312.5u',
            'quit','.endc','.end',
        ])+'\n')
        result=subprocess.run(['ngspice','-b',str(deck)],capture_output=True,text=True)
    output=result.stdout+result.stderr
    aborted=('tran simulation(s) aborted' in output or 'Timestep too small' in output
             or 'Error:' in output or result.returncode!=0)
    match=re.search(r'emax\s*=\s*([-+\d.eE]+) at=\s*([-+\d.eE]+)',output)
    rows=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',output)
    if aborted or not match or not rows or float(match.group(2))<250e-6:
        return dict(status='aborted-or-no-complete-window',data_rows=int(rows[-1]) if rows else 0,
                    timestep_failure='Timestep too small' in output)
    return dict(status='complete',data_rows=int(rows[-1]),eht_peak_v=float(match.group(1)),
                peak_time_s=float(match.group(2)))


def run(source_pdf):
    read=json.loads(READ.read_text())
    if sha(source_pdf)!=read['source_pdf_sha256']:
        raise ValueError('page-4 PDF differs from the existing T3 source read')
    graph=json.loads(GRAPH.read_text());parameters=json.loads(PARAMETERS.read_text())
    sign=json.loads(SIGN.read_text());transcription=json.loads(TRANSCRIPTION.read_text())
    with tempfile.TemporaryDirectory() as directory:
        xml=Path(directory)/'output.xml'
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                        '-o',str(xml),str(SHEET)],check=True,capture_output=True,text=True)
        pins=t3_flyback_sign.component_pins(xml,{'012-6921:T3'})['012-6921:T3']
    ports=transcription['ports']
    model_nodes={port:pins.get(str(index)) for index,port in enumerate(ports,1)}
    checks=dict(current_joined=model_nodes['X1_3']==model_nodes['X2_3']=='h_upper2',
                hv_cold_shared=model_nodes['X1_7']==model_nodes['X1_16']=='h_hvcold',
                auxiliary_ground=model_nodes['X2_5']=='0',
                drive_hot=model_nodes['X2_7']=='h_hot',
                port_count=len(pins)==len(ports))
    accepted=set(sign['accepted_candidate_ids'])
    candidates=[c for c in transformer_candidates.enumerate_candidates(graph)
                if c['id'] in accepted]
    if len(candidates)!=8 or any(c['polarity']['high_voltage']!=-1 for c in candidates):
        raise ValueError('stored sign-filter candidates differ from current graph')
    rows=[]
    for candidate in candidates:
        tied=simulate(graph,parameters,candidate,True,'flux')
        open_return=simulate(graph,parameters,candidate,False,'flux')
        rows.append(dict(candidate_id=candidate['id'],polarity=candidate['polarity'],
                         tied=tied,open=open_return,
                         tied_to_open_peak_ratio=(tied['eht_peak_v']/open_return['eht_peak_v']
                            if tied['status']==open_return['status']=='complete' and open_return['eht_peak_v']>0 else None)))
    xspice=simulate(graph,parameters,candidates[0],True,'xspice')
    passed=(all(checks.values()) and len(rows)==8
            and all(row['tied']['status']==row['open']['status']=='complete'
                    and row['tied']['eht_peak_v']>10
                    and 0<=row['open']['eht_peak_v']<.01
                    and row['tied_to_open_peak_ratio']>1000 for row in rows))
    return dict(format='dac-monitor-t3-return-variants-v1',
        qualification='conditional functional comparison of two unverified external return graphs; not an independent source confirmation, loaded EHT prediction or A1/A5 closure',
        source_pdf_sha256=sha(source_pdf),source_read_sha256=sha(READ),
        graph_sha256=sha(GRAPH),parameters_sha256=sha(PARAMETERS),
        sign_filter_sha256=sha(SIGN),sheet_sha256=sha(SHEET),
        transcription_sha256=sha(TRANSCRIPTION),
        current_model_nodes={port:model_nodes[port] for port in
                             ('X2_7','X2_5','X2_3','X1_3','X1_7','X1_16')},
        current_model_checks=checks,
        variants=[dict(id='tied',x1_3='upper2',x2_3='upper2',
                       interpretation='current KiCad hypothesis'),
                  dict(id='open',x1_3='upper_return',x2_3='upper2',
                       interpretation='source-ambiguous alternative')],
        pulse_setup='1 V positive 16 us primary pulse every 62.5 us, five pulses; isolated V21-class diode, 1 nF EHT capacitance, 200 Mohm leakage and 1 Gohm auxiliary shunts; flux backend',
        candidate_results=rows,
        xspice_tied_diagnostic=dict(candidate_id=candidates[0]['id'],result=xspice,
            limitation='The xspice backend does not complete this tied-return rectifier bench at the present settings; only the flux backend supports the functional comparison.'),
        open_checks=['Source page 4 does not independently establish X1:3-to-X2:3 continuity',
                     'Tap order, winding parameters, collector drive and connected loading remain unverified',
                     'The isolated rectifier bench cannot prove 11-12 kV EHT or any historical winding return'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.source_pdf);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['candidate_results'])} sign-compatible candidates; tied/open comparison passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
