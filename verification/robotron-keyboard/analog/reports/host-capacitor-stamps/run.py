#!/usr/bin/env python3
"""Require byte-identical replay before accepting additional capacitor-stamp logs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
analog = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--build-provenance', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
parent = json.loads((args.source/'report.json').read_text())
if (parent.get('timeStepMode') != 'represented' or parent.get('mode') != '256'
        or parent.get('integrationArithmetic') != '256'
        or parent.get('completed') is not False):
    raise ValueError('Expected the failed represented-time combined-precision capture')
provenance = json.loads(args.build_provenance.read_text())
if (provenance['auditPatchSha256'] != sha(analog/'engine-patches/ngspice-47-capacitor-stamp-audit.patch')
        or provenance['auditBaseProvenanceSha256'] != sha(args.source/'build-provenance.json')
        or provenance['auditBaseProvenance']['executableSha256'] != parent['ngspiceRuntime']['executable']['sha256']):
    raise ValueError('Logging-only build does not derive from source runtime')
runner = analog/'reports/host-represented-time/run.py'
command = [sys.executable, str(runner), str(args.source), '--time-step', 'represented',
           '--integration-arithmetic', '256', '--mode', '256',
           '--runtime', str(args.runtime), '--build-provenance', str(args.build_provenance),
           '--out', str(args.out)]
subprocess.run(command, check=True)
result = json.loads((args.out/'report.json').read_text())
matches = {name: sha(args.out/name) == digest for name, digest in parent['artifacts'].items()
           if name in ('io.cir', 'trace.txt', 'host-trace.txt', 'driver-trace.txt', 'boundary-trace.txt')}
log = (args.out/'ngspice.log').read_text()
receipt = {'qualified': False, 'reproducedEvidence': False,
           'sourceReportSha256': sha(args.source/'report.json'),
           'reportSha256': sha(args.out/'report.json'),
           'wrapperSha256': sha(__file__), 'runnerSha256': sha(runner), 'command': command,
           'identicalArtifacts': matches,
           'diagnosticEqual': result['solverDiagnostic'] == parent['solverDiagnostic'],
           'capacitorAuditRecords': sum(line.startswith('CAP_AUDIT before ') for line in log.splitlines()),
           'linearAuditRecords': sum(line.startswith('LINEAR_AUDIT begin ') for line in log.splitlines())}
receipt['reproducedEvidence'] = (len(matches) == 5 and all(matches.values())
                                 and receipt['diagnosticEqual'] and receipt['linearAuditRecords'] > 0
                                 and receipt['capacitorAuditRecords'] > 0)
(args.out/'audit-control.json').write_text(json.dumps(receipt, indent=2)+'\n')
if not receipt['reproducedEvidence']:
    raise ValueError('Additional logging did not reproduce the source capture')
print(args.out/'audit-control.json')
