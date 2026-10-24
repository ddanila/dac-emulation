"""Recognize filter-window audit records while retaining genuine solver failures."""
from startup_truncation_log import startup_truncation_record, diagnostic as startup_diagnostic


def filter_truncation_record(line):
    return line.startswith('FILTER_TRUNC error ') and startup_truncation_record(
        line.replace('FILTER_TRUNC error ', 'STARTUP_TRUNC error ', 1))


def diagnostic(log):
    return startup_diagnostic("\n".join(line for line in log.splitlines()
                                       if not filter_truncation_record(line)))
