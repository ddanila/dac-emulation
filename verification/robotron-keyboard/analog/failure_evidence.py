"""Fingerprint available failed-run outputs without interpreting them as valid traces."""
import hashlib


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
