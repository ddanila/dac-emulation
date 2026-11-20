"""Regenerate the source-constrained T3 drive/HV/G1 core without tap order."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
DRIVE = REF / 't3-drive-polarity-source-read.json'
HV = REF / 't3-hv-terminal-read.json'
G1 = REF / 't3-g1-rectifier-source-read.json'
TRANSCRIPTION = REF / 'horizontal-output-transcription.json'
OLD_FILTER = REF / 't3-g1-polarity-filter.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source_pdf):
    reads = {name: json.loads(path.read_text()) for name, path in
             [('drive', DRIVE), ('hv', HV), ('g1', G1)]}
    source_sha = sha(source_pdf)
    if any(read['source_pdf_sha256'] != source_sha for read in
           (reads['drive'], reads['g1'])):
        raise ValueError('source scan does not match the functional reads')
    if any(view['pdf_sha256'] != source_sha for view in reads['hv']['source_views']
           if view['file'] == 'older.pdf'):
        raise ValueError('source scan does not match the HV terminal read')
    if reads['drive']['source_edges']['drive_winding_endpoints'] != ['X2:7', 'X2:4']:
        raise ValueError('drive terminals changed')
    if reads['drive']['source_edges']['output_transistor_collector']['t3_terminal'] != 'X2:7':
        raise ValueError('drive collector terminal changed')
    if reads['drive']['source_edges']['damper'] != dict(part='V17', anode_net='0',
                                                        cathode_terminal='X2:7'):
        raise ValueError('collector flyback polarity evidence changed')
    if reads['hv']['source_edges'] != [
        dict(kind='winding', terminals=['X1:16', 'X1:1']),
        dict(kind='rectifier', part='V21', anode='X1:1', cathode='X1:2'),
        dict(kind='output', terminal='X1:2', net='EHT/UG3')]:
        raise ValueError('HV source path changed')
    if reads['g1']['source_edges'] != dict(
            v14_anode_net='h_g1raw', v14_cathode_t3_terminal='X2:6',
            c18_other_terminal='00', manual_tp17_terminal='V14:K'):
        raise ValueError('G1 source path changed')

    # Each pair names only the terminals needed for one documented function.
    # Their order defines the measured voltage; no other pin is joined to them.
    core = dict(drive=['X2_7', 'X2_4'], high_voltage=['X1_1', 'X1_16'],
                g1_auxiliary=['X2_6', 'X2_5'])
    transcription = json.loads(TRANSCRIPTION.read_text())
    ports = transcription['ports']
    represented = [pin for pair in core.values() for pin in pair]
    if len(set(represented)) != 6 or not set(represented) <= set(ports):
        raise ValueError('functional core is inconsistent with assembly ports')
    if any(transcription['port_nets'].get(pin) != net for pin, net in
           dict(X2_7='h_hot', X2_4='h_return', X2_5='0',
                X2_6='h_sync', X1_16='h_hvcold').items()):
        raise ValueError('functional terminal assembly mapping changed')
    old = json.loads(OLD_FILTER.read_text())
    old_retained = [row for row in old['candidate_results'] if row['compatible']]
    if len(old_retained) != 4 or any(
            row['polarity']['high_voltage'] != -1 or row['polarity']['auxiliary'] != 1
            for row in old_retained):
        raise ValueError('prior conditional sign result changed')
    candidates = [dict(high_voltage_sign=hv_sign, g1_auxiliary_sign=g1_sign,
                       retained=hv_sign == 1 and g1_sign == -1)
                  for hv_sign, g1_sign in itertools.product((-1, 1), repeat=2)]
    return dict(
        format='dac-monitor-t3-functional-core-v1',
        qualification='source-constrained six-terminal core only; no full T3 graph, ratios or source-circuit operating point',
        source_pdf_sha256=source_sha,
        source_read_sha256={name: sha(path) for name, path in
                            [('drive', DRIVE), ('hv', HV), ('g1', G1)]},
        transcription_sha256=sha(TRANSCRIPTION), previous_filter_sha256=sha(OLD_FILTER),
        voltage_reference=dict(drive='V(X2:7)-V(X2:4)',
                               high_voltage='V(X1:1)-V(X1:16)',
                               g1_auxiliary='V(X2:6)-V(X2:5)'),
        functional_pairs=core,
        functional_rules=[
            'Positive X2:7-to-X2:4 flyback must make X1:1 positive relative to X1:16 so V21 charges EHT.',
            'With the X2:5-to-00 return hypothesis, the same flyback must make X2:6 negative relative to X2:5 so V14 charges negative G1.'
        ],
        candidates=candidates,
        retained_candidates=[row for row in candidates if row['retained']],
        unassigned_assembly_terminals=[pin for pin in ports if pin not in represented],
        crosscheck='The retained pair signs correspond to the earlier four candidates after reversing the HV and auxiliary tap-list orientation; upper/lower signs are not inferred here.',
        unresolved=[
            'X2:5 return and X2:5-to-X2:6 winding continuity are not source-qualified; G1 sign is conditional on both.',
            'The thirteen remaining assembly terminals and all internal continuities, tap signs and ratios are unassigned.',
            'A full multi-winding equivalent needs independently bounded ratios, loss and parasitics before it can replace T3.'
        ],
        passed=len([row for row in candidates if row['retained']]) == 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['retained_candidates'])}/{len(report['candidates'])} functional core candidates remain")
    raise SystemExit(0 if report['passed'] else 2)
