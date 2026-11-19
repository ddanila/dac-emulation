"""Record the provisional P09A/LM709-family model's DC follower response."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'devices/lm709-family.cir'
INPUTS = (-1, 0, 1)


def run():
    model = MODEL.read_text()
    cases = []
    for vin in INPUTS:
        deck = f'''* P09A provisional model: compensated DC follower
{model}
Vp vp 0 15
Vm vm 0 -15
Vi input 0 {vin}
Xamp ca output input vm co raw vp cb LM709_FAMILY
C1 ca comp 5n
R1 comp cb 1.5k
C2 co raw 200p
R2 raw output 51
Rl output 0 2k
.control
op
print v(output) i(Vp)
.endc
.end
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'follower.cir'
            path.write_text(deck)
            result = subprocess.run(['ngspice', '-b', str(path)],
                                    capture_output=True, text=True, timeout=30)
        if result.returncode or re.search(r'error|warning|singular matrix',
                                          result.stdout + result.stderr, re.I):
            raise RuntimeError('DC follower solve failed: ' + result.stdout + result.stderr)
        output = re.search(r'^v\(output\) = ([^\s]+)', result.stdout, re.M)
        supply = re.search(r'^i\(vp\) = ([^\s]+)', result.stdout, re.M)
        if not output or not supply:
            raise RuntimeError('DC follower output missing: ' + result.stdout)
        vout = float(output.group(1))
        cases.append(dict(input_v=vin, output_v=vout,
                          error_v=vout - vin, positive_supply_current_a=-float(supply.group(1)),
                          tracking_within_50mv=abs(vout - vin) <= .05))
    return dict(format='dac-monitor-lm709-dc-follower-check-v1',
                qualification='isolated A2 failure diagnostic for an unqualified P09A substitute; the 50 mV threshold is a generous functional check, not a P09A factory limit',
                comparator='National/TI LM709C, SNOS659A, electrical characteristics at +/-15 V, 2 kohm load and unity-gain compensation; original P09A identity remains unverified',
                comparator_url='https://media.digikey.com/pdf/Data%20Sheets/Texas%20Instruments%20PDFs/LM709.pdf',
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                setup=dict(rails_v=[-15, 15], load_ohm=2000,
                           input_compensation_f=5e-9, input_compensation_ohm=1500,
                           output_compensation_f=200e-12, output_series_ohm=51),
                cases=cases, passed=all(case['tracking_within_50mv'] for case in cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{sum(case['tracking_within_50mv'] for case in report['cases'])}/"
          f"{len(report['cases'])} DC follower cases track within 50 mV")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
