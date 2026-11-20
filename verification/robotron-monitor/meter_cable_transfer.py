"""Bound what the unvalued page-16 measuring-cable inset can establish.

The lower terminals are not connected inside the inset. The RC cases below
are explicitly conditional on a shared return and an ideal series capacitor;
they do not assign a value or a meter mode to the historical cable.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_READ = ROOT/'reference/k7222-11/page16-meter-cable-source-read.json'
PDF = ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
OPERATION = ROOT.parents[1]/'build/monitor/phase-a/sources/older-operation.pdf'
SOURCE_MANIFEST = ROOT/'sources.json'
CAPACITANCES_F = (10e-12, 100e-12, 1e-9)
FREQUENCIES_HZ = (1/0.0195, 16000)
METER_CASES = {'ac_mv_1meg': 1e6, 'dc_mv_10meg': 1e7}


def gain(frequency_hz, capacitance_f, load_ohm, source_ohm=0):
    """Magnitude of Rload/(Rsource + 1/(jωC) + Rload)."""
    if frequency_hz < 0 or capacitance_f <= 0 or load_ohm <= 0 or source_ohm < 0:
        raise ValueError('invalid conditional RC parameter')
    if frequency_hz == 0:
        return 0.
    reactance = 1/(2*math.pi*frequency_hz*capacitance_f)
    return load_ohm/math.hypot(load_ohm+source_ohm, reactance)


def minimum_c_for_gain(frequency_hz, load_ohm, target=0.9):
    """Best-case series C with zero source impedance for target AC gain."""
    if frequency_hz <= 0 or load_ohm <= 0 or not 0 < target < 1:
        raise ValueError('invalid threshold case')
    return target/(2*math.pi*frequency_hz*load_ohm*math.sqrt(1-target*target))


def run():
    source = json.loads(SOURCE_READ.read_text())
    manifest = {item['file']: item['sha256'] for item in
                json.loads(SOURCE_MANIFEST.read_text())['sources']}
    pdf_hash = manifest['older.pdf']
    if pdf_hash != source['source_views'][0]['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-16 read')
    operation_hash = manifest['older-operation.pdf']
    for local, expected in ((PDF, pdf_hash), (OPERATION, operation_hash)):
        if local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() != expected:
            raise ValueError('local PDF differs from source manifest: '+local.name)
    cases = []
    for mode, load in METER_CASES.items():
        for frequency in FREQUENCIES_HZ:
            cases.append(dict(meter_case=mode, load_ohm=load,
                              frequency_hz=frequency,
                              conditional_gain_by_capacitance_f={
                                  str(cap): gain(frequency, cap, load)
                                  for cap in CAPACITANCES_F},
                              minimum_series_capacitance_f_for_90pct_best_case_gain=
                              minimum_c_for_gain(frequency, load)))
    return dict(format='dac-monitor-meter-cable-transfer-bound-v1',
                status='conditional structural bound; original cable transfer still unknown',
                source_pdf_sha256=pdf_hash,
                operation_pdf_sha256=operation_hash,
                operation_instruction='PDF page 30, printed page 28: connect the neck board through measuring cable 1.11.017154.0 to a digital voltmeter; set 0.1 mV rise and 3.6 mV bright. No meter model or AC/DC setting is given.',
                source_read_sha256=hashlib.sha256(SOURCE_READ.read_bytes()).hexdigest(),
                comparator=dict(source='https://assets.fluke.com/manuals/884xa___umeng0300.pdf',
                    instrument='Fluke 8845A/8846A, not the unspecified Robotron service meter',
                    dc_100mv_default_input_ohm=1e7,
                    dc_100mv_optional_high_impedance_ohm_min=1e10,
                    ac_100mv_input_ohm=1e6,
                    ac_meter='AC-coupled true RMS; 3-300 kHz slow filter, 20-300 kHz medium, 200-300 kHz fast'),
                model=dict(topology='assumed common lower return, ideal series C, zero-ohm source and resistive meter input',
                    equation='|H(jω)|=Rmeter/sqrt((Rsource+Rmeter)^2+(1/(ωCseries))^2)',
                    dc_gain=0, series_capacitance_f='unknown; 10 pF, 100 pF and 1 nF are sensitivity cases, not bounds or assigned cable values',
                    field_frequency_hz=FREQUENCIES_HZ[0], line_frequency_hz=FREQUENCIES_HZ[1]),
                cases=cases,
                conclusion='For the literal common-return passive RC interpretation, a steady DC meter reading cannot follow X3 through the series capacitor. The manual says only digital voltmeter and does not specify AC/DC mode. The inset leaves both lower connections and both shunt values unassigned, so neither the 0.1 mV rise nor 3.6 mV target can be predicted from a direct X3 DC value. The RC cases are upper-envelope sensitivities, not a reconstruction of cable 1.11.017154.0.',
                remaining=['Identify the actual cable element values and lower-terminal connections or keep topology conditional.',
                           'Identify meter mode, impedance, bandwidth and integration window before scoring the service readings.',
                           'Run the native grid with qualified tube emission and the specified control sequence.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('meter-cable conditional DC gain:', result['model']['dc_gain'])
