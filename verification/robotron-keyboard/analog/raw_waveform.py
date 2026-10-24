"""Read real native-endian ngspice binary samples without loading the waveform."""
import math
import struct


def header(stream):
    fields, variables = {}, []
    in_variables = False
    for _ in range(4096):
        line = stream.readline(4096)
        if not line.endswith(b'\n'):
            raise ValueError('Missing or oversized raw header')
        text = line.decode('ascii').strip()
        if text == 'Binary:':
            break
        if text == 'Variables:':
            in_variables = True
        elif in_variables:
            parts = text.split()
            if len(parts) != 3 or int(parts[0]) != len(variables):
                raise ValueError('Invalid raw variable table')
            variables.append(parts[1])
        else:
            key, sep, value = text.partition(':')
            if not sep or key in fields:
                raise ValueError('Invalid raw header field')
            fields[key] = value.strip()
    else:
        raise ValueError('Oversized raw header')
    if fields.get('Flags') != 'real' or fields.get('Plotname') != 'Transient Analysis':
        raise ValueError('Expected real transient raw output')
    if int(fields['No. Variables']) != len(variables) or not variables or variables[0] != 'time':
        raise ValueError('Invalid raw observation scope')
    count = int(fields['No. Points'])
    if count < 0 or len(set(variables)) != len(variables):
        raise ValueError('Invalid raw count or duplicate variables')
    return variables, count


def rows(stream, width, expected_count):
    """Require a separately verified log count when the pipe header count is zero."""
    if width < 2 or expected_count < 2:
        raise ValueError('Invalid required raw dimensions')
    row = struct.Struct('=' + 'd' * width)
    last = -math.inf
    for _ in range(expected_count):
        data = stream.read(row.size)
        if len(data) != row.size:
            raise ValueError('Truncated raw waveform')
        values = row.unpack(data)
        if not all(map(math.isfinite, values)) or values[0] <= last:
            raise ValueError('Nonfinite or nonmonotonic raw waveform')
        last = values[0]
        yield values
    if stream.read(1):
        raise ValueError('Trailing raw waveform data')
