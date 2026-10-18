"""Account for every reference component without conflating coverage with fidelity."""


def classify(components, electrical_models, electrical_matrix, electrical_outputs, resolved_bus=False, boundaries=None):
    boundaries = boundaries or {}
    if set(boundaries) & set(electrical_models):
        raise ValueError("A component cannot be both an electrical model and an excluded boundary")
    digital = {
        'A1': '7406 HDL logic; selected output pins use nominal electrical sink models',
        'A2.1': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A2.2': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A2.3': 'DL003 HDL logic; column pins use electrical sinks in matrix mode',
        'A4': '8282 HDL latch and bus; nominal input load in matrix mode',
        'A5': 'TV80 CPU; digital buses/control pins, nominal clock/reset input loads',
        'A6': 'DL074 HDL flip-flops; nominal electrical LED output drive in output mode',
        'A8': ('U556/2716 pin-mapped ROM on resolved CPU/latch bus' if resolved_bus
               else 'S600 ROM array directly feeding CPU input; diagnostic bypass'),
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
        elif ref in boundaries:
            domain, model = 'boundary', boundaries[ref]
        elif ref in digital:
            domain, model = 'digital-or-interface', digital[ref]
        elif ref in matrix_refs and not electrical_matrix:
            domain, model = 'boundary', 'Collapsed digital contact/row OR model'
        elif ref in output_refs and not electrical_outputs:
            domain, model = 'boundary', 'Digital output observation; electrical load omitted'
        else:
            raise ValueError('Unclassified board component: ' + ref)
        result[ref] = {'referenceType': component['type'], 'domain': domain, 'model': model}
    extra = (set(electrical_models) | set(boundaries)) - set(components)
    if extra:
        raise ValueError('Model/boundary names absent from schematic: ' + ', '.join(sorted(extra)))
    return {'components': result,
            'meaning': 'Explicit implementation/boundary inventory, not device-model or full-board qualification',
            'remainingFidelityGaps': ['Uncharacterized semiconductor, gate, cable and filter parameters',
                                     'Electrical bus currents, pin delays and calibrated control-pullup loading',
                                     'Controller IC supply-current and brownout behavior',
                                     'Specimen key construction, firmware and physical routing']}


def classify_service(components, electrical_models, cpu_pullups=False, logic_pullups=False):
    """Explicit exclusions for the CPU-side BR service fixture, not the full board."""
    from reset_probe import RESET_REFS
    from oscillator_probe import OSCILLATOR_REFS

    boundaries = {ref: 'Reset generator excluded by the BR2 service fixture; no electrical or supply-current contribution'
                  for ref in RESET_REFS}
    boundaries.update({ref: 'Oscillator excluded by the BR1 service fixture; no electrical or supply-current contribution'
                       for ref in (*OSCILLATOR_REFS, 'A7')})
    boundaries.update({'BR1': 'Virtual open bridge; CPU clock supplied by the HDL service boundary',
                       'BR2': 'Virtual open bridge; CPU reset supplied by the HDL service boundary'})
    for enabled, refs in ((cpu_pullups, ('R6.4', 'R6.5')), (logic_pullups, ('R6.3', 'R6.6', 'R9.9'))):
        if any((ref in electrical_models) != enabled for ref in refs):
            raise ValueError('Control model coverage differs from enabled service options')
    result = classify(components, electrical_models, True, True, True, boundaries)
    c = result['components']
    c['A5']['model'] = ('TV80 CPU with externally supplied digital service clock/reset; resolved digital data bus; '
                        + ('electrical interrupt/NMI/wait and bus-request pullups with reference-maximum input capacitance'
                           if cpu_pullups else 'interrupt/NMI/wait and bus request held high')
                        + '; no package supply-current or brownout model')
    if logic_pullups:
        c['A2.2']['model'] = 'DL003 HDL logic with nominal electrical sinks for columns, latch enable and I/O active'
        c['A4']['model'] = '8282 HDL latch/bus; electrical enable and strobe receivers, nominal matrix input load'
        c['A6']['model'] = 'DL074 HDL flip-flops; electrical async-control and clock receivers, nominal LED output drive'
    result['meaning'] = 'BR service-fixture implementation/boundary inventory; excluded clock/reset circuits are not simulated'
    return result
