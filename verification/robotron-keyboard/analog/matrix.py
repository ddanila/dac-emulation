"""Reference sensing front end and an explicit external contact-matrix fixture."""
import re
from circuit import elements, node, nominal_models


def matrix_circuit(components, contact_ohms=100, beta=100, include_models=True):
    pins = components['X1']['pins']
    rows, columns = {}, {}
    for pin, name in pins.items():
        match = re.fullmatch(r'/((?:ROW)|(?:COL))(\d+)', name or '')
        if match:
            mapping = rows if match[1] == 'ROW' else columns
            index = int(match[2])
            if index in mapping:
                raise ValueError('Duplicate matrix connector net')
            mapping[index] = {'pin': pin, 'net': name}
    if set(rows) != set(range(8)) or set(columns) != set(range(13)):
        raise ValueError('Unexpected matrix connector dimensions')
    refs = ['R1', 'R2', *[f'R9.{i}' for i in range(1, 9)], *[f'V4.{i}' for i in range(1, 9)]]
    lines, models = elements(components, refs)
    if include_models:
        lines += nominal_models(beta)
    lines += [f'.model CONTACT_NOMINAL SW(RON={contact_ohms} ROFF=1t VT=2.5 VH=0)',
              '.model SINK_NOMINAL SW(RON=20 ROFF=1t VT=2.5 VH=0)']
    contacts = []
    for col, column in sorted(columns.items()):
        cn = node(column['net'])
        lines.append(f'Sdriver{col} {cn} 0 sink{col} 0 SINK_NOMINAL')
        for row, row_info in sorted(rows.items()):
            index = col*8+row
            lines.append(f'Scontact{index} {cn} {node(row_info["net"])} contact{index} 0 CONTACT_NOMINAL')
            contacts.append({'index': index, 'column': col, 'row': row,
                             'connectorPins': [column['pin'], row_info['pin']]})
    outputs = []
    for row in range(8):
        sense = node(components['A4']['pins'][str(row+1)])
        if sense != f'n_SENSE{row}':
            raise ValueError('Unexpected latch sense pin mapping')
        outputs.append(sense)
        lines += [f'Rlatch{row} {sense} 0 1g', f'Clatch{row} {sense} 0 10p']
    return lines, {'models': models, 'contacts': contacts, 'outputs': outputs,
                   'columnNets': [node(columns[i]['net']) for i in range(13)]}


def reached_rows(contacts, selected_columns):
    """Independent connectivity oracle for the diode-free external test fixture."""
    columns, rows = set(selected_columns), set()
    while True:
        next_rows = rows | {index % 8 for index in contacts if index // 8 in columns}
        next_columns = columns | {index // 8 for index in contacts if index % 8 in next_rows}
        if next_columns == columns and next_rows == rows:
            return rows
        columns, rows = next_columns, next_rows
