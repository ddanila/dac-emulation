"""Run live ngspice with optional lossless output capture and failure receipts."""
import re
import subprocess
from compressed_output import capture


class ProducerFailed(Exception):
    pass


def run(command, directory, env, log, timeout, deck, *, compressed=False):
    names = re.findall(r'^wrdata\s+(\S+)\s+', deck, re.M)
    if compressed and (not names or len(set(names)) != len(names) or
                       any('/' in n or n in ('.', '..') for n in names)):
        raise ValueError('Compressed output requires unique local wrdata names')
    code, timed_out, error, records = None, False, None, {}
    try:
        with capture(directory, names, enabled=compressed) as records:
            try:
                code = subprocess.run(command, cwd=directory, env=env, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                raise ProducerFailed()
            if code != 0:
                raise ProducerFailed()
    except ProducerFailed:
        # Exit the context exceptionally so unopened FIFOs cannot delay cleanup.
        pass
    except (ValueError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
    return code, timed_out, error, records
