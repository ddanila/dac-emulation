"""Account for every reference component without conflating coverage with fidelity."""


def classify(components, electrical_models, electrical_matrix, electrical_outputs):
    digital = {
        'A1': '7406 HDL logic; selected output pins use nominal electrical sink models',
        'A2.1': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A2.2': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A2.3': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A4': '8282 HDL latch and bus; nominal input load in matrix mode',
        'A5': 'TV80 CPU; digital buses/control pins, nominal clock/reset input loads',
        'A6': 'DL074 HDL flip-flops; nominal electrical LED output drive in output mode',
        'A8': 'S600 ROM array; mirrored address decode and digital data bus',
        'R6.3': 'HDL pullup on latch output enable; no electrical loading',
        'R6.4': 'CPU interrupt/NMI/wait tie-high boundary; no electrical loading',
        'R6.5': 'CPU bus-request tie-high boundary; no electrical loading',
        'R6.6': 'HDL pullup on flip-flop preset/clear; no electrical loading',
        'R9.9': 'HDL pullup on I/O active; no electrical loading',
        'X1': 'Matrix/LED external fixture; bus-request contact remains open',
        'XT1': 'External cable/load boundary; shield remains unconnected',
    }
    matrix_refs = {'R1', 'R2', *[f'R9.{i}' for i in range(1, 9)], *[f'V4.{i}' for i in range(1, 9)]}
    output_refs = {'R10.1', 'R10.2', 'R11.1', 'R11.2', 'C3.1', 'C3.2',
                   *[f'C5.{i}' for i in range(1, 6)], *[f'L1.{i}' for i in range(1, 5)]}
    result = {}
    for ref, component in components.items():
        if ref in electrical_models:
            domain, model = 'electrical', electrical_models[ref]
        elif ref in digital:
            domain, model = 'digital-or-interface', digital[ref]
        elif ref in matrix_refs and not electrical_matrix:
            domain, model = 'boundary', 'Collapsed digital contact/row OR model'
        elif ref in output_refs and not electrical_outputs:
            domain, model = 'boundary', 'Digital output observation; electrical load omitted'
        else:
            raise ValueError('Unclassified board component: ' + ref)
        result[ref] = {'referenceType': component['type'], 'domain': domain, 'model': model}
    extra = set(electrical_models) - set(components)
    if extra:
        raise ValueError('Electrical model names absent from schematic: ' + ', '.join(sorted(extra)))
    return {'components': result,
            'meaning': 'Explicit implementation/boundary inventory, not device-model or full-board qualification',
            'remainingFidelityGaps': ['Uncharacterized semiconductor, gate, cable and filter parameters',
                                     'Digital CPU/peripheral buses and control pullups',
                                     'Controller IC supply-current and brownout behavior',
                                     'Specimen key construction, firmware and physical routing']}
