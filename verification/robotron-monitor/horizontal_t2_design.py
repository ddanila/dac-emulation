"""Bound T2 primary operation and expose the unloaded driver-stage TP15 gap."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile

import reference

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'profiles/k7222-11-horizontal-oscillator.json'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
OBSERVATIONS=ROOT/'reference/k7222-11/service-observations.json'
SOURCE=ROOT/'reference/k7222-11/page3-t2-primary-source-read.json'
MODEL=ROOT/'circuits/k7222-11-horizontal-models.cir'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    parts={part['id']:part for part in json.loads(INVENTORY.read_text())['parts']}
    r23=parts['012-6921:R23']
    if r23['value']!=62:raise ValueError('R23 changed: rederive T2 primary bounds')
    source=json.loads(SOURCE.read_text())
    if source['source']['pdf_sha256']!='3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd':
        raise ValueError('unexpected T2 source PDF')
    profile=json.loads(PROFILE.read_text())
    params=profile['parameters']
    line_hz=16000
    minimum_l=5*r23['value']/(2*math.pi*line_hz)
    maximum_r=.1*r23['value']
    manual=next(item for item in json.loads(OBSERVATIONS.read_text())['waveforms']
                if item.get('test_point')==15)
    if manual['model_node']!='h_drivecol':raise ValueError('TP15 mapping changed')
    target=manual['approximate_swing_v']
    tolerance=manual['acceptance_tolerance']
    cases={
        'nominal':{},
        'minimum_primary_l':{'horizontal_driver_l':params['horizontal_driver_l']['minimum']},
        'maximum_primary_l':{'horizontal_driver_l':params['horizontal_driver_l']['maximum']},
        'minimum_primary_r':{'horizontal_driver_r':params['horizontal_driver_r']['minimum']},
        'maximum_primary_r':{'horizontal_driver_r':params['horizontal_driver_r']['maximum']},
        'minimum_ratio':{'horizontal_driver_ratio':params['horizontal_driver_ratio']['minimum']},
        'maximum_ratio':{'horizontal_driver_ratio':params['horizontal_driver_ratio']['maximum']},
        'minimum_driver_coupling':{'horizontal_driver_coupling':params['horizontal_driver_coupling']['minimum']},
        'maximum_driver_coupling':{'horizontal_driver_coupling':params['horizontal_driver_coupling']['maximum']},
    }
    results={};primary_nets=None
    with tempfile.TemporaryDirectory() as directory:
        for name,changes in cases.items():
            out=Path(directory)/name
            stage=reference.run(PROFILE,out,stop=.005,step=1e-6,changes=changes)
            rows=reference.read_samples(out/'samples.txt',stage['probes'],0,.005,1e-6)
            names=['time']+[probe['name'] for probe in stage['probes']]
            late=[row for row in rows if row[0]>.003]
            if len(late)<100:raise ValueError('too few late driver-stage samples')
            def span(name):
                values=[row[names.index(name)] for row in late]
                return max(values)-min(values)
            results[name]=dict(changes=changes,collector_vpp=span('collector'),
                               unloaded_secondary_vpp=span('secondary'),
                               primary_l_h=params['horizontal_driver_l']['nominal'] if 'horizontal_driver_l' not in changes else changes['horizontal_driver_l'],
                               primary_r_ohm=params['horizontal_driver_r']['nominal'] if 'horizontal_driver_r' not in changes else changes['horizontal_driver_r'])
            if name=='nominal':
                component=next(part for part in stage['components'] if part['source_id']=='012-6921:T2')
                primary_nets=component['nodes'][:2]
    expected=[source['model_pin_nets'][key] for key in ('top','collector')]
    passed=(primary_nets==expected and params['horizontal_driver_l']['minimum']>=minimum_l
            and params['horizontal_driver_r']['maximum']<=maximum_r+1e-12
            and all(result['collector_vpp']>0 and result['unloaded_secondary_vpp']>0
                    for result in results.values()))
    nominal=results['nominal']['collector_vpp']
    return dict(format='dac-monitor-horizontal-t2-design-v1',
        qualification='conditional T2 primary operating bounds and isolated oscillator/driver sensitivity; no V18 loading, original transformer data or connected A3 score',
        source_read_sha256=sha(SOURCE),profile_sha256=sha(PROFILE),
        model_sha256=sha(MODEL),inventory_sha256=sha(INVENTORY),
        observations_sha256=sha(OBSERVATIONS),
        documented=dict(r23_ohm=r23['value'],r23_source=r23['source'],
                        line_frequency_hz=line_hz,tp15_v13_collector_guideline_vpp=target,
                        tp15_range_vpp=[target*(1-tolerance),target*(1+tolerance)],
                        tp15_source=manual['source']),
        design_rules=dict(minimum_primary_l_h_for_reactance_five_times_r23=minimum_l,
                          maximum_primary_r_ohm_for_ten_percent_added_series_drop=maximum_r,
                          equations=['2*pi*f*L_primary >= 5*R23', 'R_primary <= 0.1*R23']),
        source_primary_model_nodes=primary_nets,source_primary_expected_nodes=expected,
        cases=results,
        nominal_isolated_tp15_in_manual_range=target*(1-tolerance)<=nominal<=target*(1+tolerance),
        open_checks=['The nominal isolated driver collector swing misses the manual TP15 guideline; the bench omits V18 base/output loading and cannot score A3',
                     'T2 secondary ratio, resistance, coupling and polarity have no qualified source-derived bounds',
                     'The page-3/4 seam and secondary terminal numbers need an independent source comparison',
                     'The original T2 copper/core loss, saturation and thermal limits are unknown'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['cases'])} isolated cases; nominal collector {report['cases']['nominal']['collector_vpp']:.2f} Vpp; design check passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
