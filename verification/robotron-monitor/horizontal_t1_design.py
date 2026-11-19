"""Check the provisional T1 half-winding against source timing and the live oscillator."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile

import reference

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'profiles/k7222-11-horizontal-oscillator.json'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
OBSERVATIONS=ROOT/'reference/k7222-11/service-observations.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def period_from_samples(path,probes,step):
    names=['time']+[p['name'] for p in probes]
    drive=names.index('drive')
    rows=reference.read_samples(path,probes,0,.005,step)
    late=[row for row in rows if row[0]>.003]
    crossings=[]
    for before,after in zip(late,late[1:]):
        if before[drive]<.3<=after[drive]:
            crossings.append(before[0]+(after[0]-before[0])*(.3-before[drive])/(after[drive]-before[drive]))
    if len(crossings)<20:raise ValueError('autonomous oscillator has too few late drive crossings')
    cycles=[b-a for a,b in zip(crossings,crossings[1:])]
    period=statistics.median(cycles)
    return dict(period_s=period,frequency_hz=1/period,late_crossings=len(crossings),
                cycle_period_range_s=[min(cycles),max(cycles)])


def run():
    inventory={part['id']:part for part in json.loads(INVENTORY.read_text())['parts']}
    cap=inventory['012-6921:C16']
    if cap['value']!=1e-7 or cap['tolerance_percent']!=10:
        raise ValueError('C16 source value changed; rederive T1')
    observed=json.loads(OBSERVATIONS.read_text())
    range_item=next(item for item in observed['manual_targets']
                    if item.get('quantity')=='horizontal_generator_control_range')
    lower_hz=range_item['minimum']*1000;upper_hz=range_item['maximum']*1000
    target_hz=1/6.25e-5
    ideal=1/((2*math.pi*target_hz)**2*cap['value'])
    ideal_range=[1/((2*math.pi*upper_hz)**2*cap['value']*1.1),
                 1/((2*math.pi*lower_hz)**2*cap['value']*.9)]
    cases=[('former_default',{'horizontal_tank_l':.0009},1e-6),
           ('low_inductance',{'horizontal_tank_l':.0014},1e-6),
           ('current_nominal',{'horizontal_tank_l':.00145},1e-6),
           ('nominal_fine',{'horizontal_tank_l':.00145},5e-7),
           ('high_inductance',{'horizontal_tank_l':.0018},1e-6),
           ('low_winding_resistance',{'horizontal_tank_l':.00145,'horizontal_tank_r':.1},1e-6),
           ('high_winding_resistance',{'horizontal_tank_l':.00145,'horizontal_tank_r':5},1e-6),
           ('low_coupling',{'horizontal_tank_l':.00145,'horizontal_tank_coupling':.95},1e-6),
           ('high_coupling',{'horizontal_tank_l':.00145,'horizontal_tank_coupling':.9999},1e-6),
           ('low_r24_trim',{'horizontal_tank_l':.00145,'horizontal_trim_fraction':.1},1e-6),
           ('high_r24_trim',{'horizontal_tank_l':.00145,'horizontal_trim_fraction':.9},1e-6)]
    results={}
    with tempfile.TemporaryDirectory() as directory:
        previous_profile=Path(directory)/'former-default-profile.json'
        old=json.loads(PROFILE.read_text())
        old['parameters']['horizontal_tank_l'].update(nominal=.0009,minimum=.0009)
        previous_profile.write_text(json.dumps(old))
        for name,changes,step in cases:
            out=Path(directory)/name
            stage=reference.run(previous_profile if name=='former_default' else PROFILE,
                                out,stop=.005,step=step,changes=changes)
            results[name]=dict(changes=changes,step_s=step,
                               **period_from_samples(out/'samples.txt',stage['probes'],step))
    nominal=results['current_nominal']['frequency_hz']
    fine=results['nominal_fine']['period_s']
    coarse=results['current_nominal']['period_s']
    passed=(lower_hz<=nominal<=upper_hz
            and results['former_default']['frequency_hz']>upper_hz
            and results['low_inductance']['period_s']<coarse<results['high_inductance']['period_s']
            and abs(coarse/fine-1)<.01)
    return dict(format='dac-monitor-horizontal-t1-design-v1',
        qualification='conditional T1 half-winding design check in autonomous source-connected oscillator; not a T1 measurement, full-stage calibration or B2 pass',
        source_pdf_sha256='3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd',
        profile_sha256=sha(PROFILE),inventory_sha256=sha(INVENTORY),
        observations_sha256=sha(OBSERVATIONS),
        documented=dict(c16_f=cap['value'],c16_tolerance_percent=cap['tolerance_percent'],
            c16_source=cap['source'],manual_frequency_range_hz=[lower_hz,upper_hz],
            manual_frequency_source=range_item['source'],native_line_period_s=6.25e-5,
            native_line_period_basis='46.5 us write + 16.0 us retrace, manual page 5'),
        ideal_lc_half_winding_h=dict(nominal=ideal,range_from_frequency_and_c16_tolerance=ideal_range,
            equation='1/((2*pi*f)^2*C16)',
            limitation='C16 is coupled through R21 and the source-connected transistor network; this is a scale, not the exact T1 inductance'),
        nominal_half_inductance_h=.00145,
        stage_to_ideal_lc_factor=.00145/ideal,
        former_default_note='Counterfactual 0.9 mH run uses a temporary copy of the old profile bound; it is outside the current live bound.',
        cases=results,nominal_inside_manual_range=lower_hz<=nominal<=upper_hz,
        former_default_outside_manual_range=results['former_default']['frequency_hz']>upper_hz,
        open_checks=['The T1 core, winding resistance and magnetic coupling have no printed electrical data',
                     'The oscillator transistor model and R41/R43 thermistor mapping remain provisional',
                     'R24 endpoint trim tests do not span the whole manual control range; native connected synchronization needs Phase B scoring',
                     'The T1-only coupling sweep does not establish original T1 magnetic properties'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['cases'])} autonomous cases; nominal {report['cases']['current_nominal']['frequency_hz']:.1f} Hz; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
