"""Fingerprint available failed-run outputs without interpreting them as valid traces."""
import hashlib
import re


def capture(directory, names):
    result = {}
    for name in names:
        path = directory / name
        try:
            digest = hashlib.sha256()
            size = 0
            # Only this invocation's raw outputs: an older .gz is not a fallback.
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(chunk)
                    digest.update(chunk)
            result[name] = {'status': 'retained', 'bytes': size, 'sha256': digest.hexdigest()}
        except FileNotFoundError:
            result[name] = {'status': 'missing'}
        except OSError as error:
            # Preserve the original simulator/validation failure in the caller.
            result[name] = {'status': 'unreadable', 'error': str(error)}
    return result


def solver_diagnostic(log):
    """Retain unlabelled abort/time-order messages even when ngspice exits zero.

    The time-order message also covers equal timestamps in ngspice 47. Reject it
    as unresolved evidence; its text alone does not prove backward execution.
    """
    # Read-only `option` output in ngspice 47, not a solver diagnostic.
    informational = {
        'Truncation error correction, charge based, is selected:',
        'Truncation error correction, voltage based, is selected:',
    }
    log = '\n'.join(line for line in log.splitlines() if line not in informational)
    match = re.search(r'^.*(?:warning|error|failed|fatal|singular|no vlog_startup_routines|'
                      r'timestep too small|simulation\(s\) aborted|XSPICE time is behind vtime).*$',
                      log, re.I | re.M)
    return match.group(0) if match else None
