"""Recognize numeric startup-audit records without changing generic failure parsing."""
import re
from failure_evidence import solver_diagnostic

def startup_truncation_record(line):
    """Recognize only the exact finite-valued arithmetic audit record."""
    scalar = r'-?0x[0-9a-f]+(?:\.[0-9a-f]+)?p[+-][0-9]+'
    keys = ('time state delta dt0 dt1 dt2 order before proposed currenttol '
            'chargetol abstol reltol chgtol difference q0 q1 q2 q3').split()
    pattern = 'STARTUP_TRUNC error ' + ' '.join(
        key + '=' + (r'[0-9]+' if key in ('state', 'order') else scalar) for key in keys)
    return re.fullmatch(pattern, line) is not None



def diagnostic(log):
    return solver_diagnostic("\n".join(line for line in log.splitlines() if not startup_truncation_record(line)))
