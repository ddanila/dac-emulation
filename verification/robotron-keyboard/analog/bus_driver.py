"""Linear bus-drive stress fixture derived from published output test points."""
import math
from bus_load import wiring as load_wiring
from circuit import node


def wiring(components, limits, unknown_pf):
    lines, report = load_wiring(components, limits, unknown_pf)
    drivers = []
    for index, (ref, supply_pin) in enumerate((('A5', '11'), ('A8', '24'), ('A4', '20'))):
        supply = components[ref]['pins'][supply_pin]
        if supply != '/+5V':
            raise ValueError('Unexpected bus driver supply: ' + ref)
        profile = limits['profiles'][components[ref]['type']]
        low, high = profile['outputLow'], profile['outputHigh']
        # Straight lines through two DC load-test endpoints are deliberately a
        # stress fixture. They are not extracted transistor or pin I/V curves.
        rlow = low['maximumVolts'] / low['sinkAmps']
        rhigh = (5 - high['minimumVolts']) / high['sourceMagnitudeAmps']
        if not all(math.isfinite(value) and value > 0 for value in (rlow, rhigh)):
            raise ValueError('Invalid bus driver test point')
        for bit in range(8):
            net = f'n_D{bit}'
            number = 8 * index + bit
            lines.extend([
                f'Bbus_low_{number} {net} 0 I=V({net})*V(bus_low_{number})/(5*{rlow:.17g})',
                f'Bbus_high_{number} {node(supply)} {net} I=(V({node(supply)})-V({net}))*V(bus_high_{number})/(5*{rhigh:.17g})',
            ])
        drivers.append({'reference': ref, 'lowOhms': rlow, 'highOhms': rhigh,
                        'profile': components[ref]['type'], 'source': profile['source']})
    report.update(drivers=drivers, nominalSupplyVolts=5, capacitanceBoundary=report['boundary'],
                  boundary='Drive is a 5 V linear endpoint stress fixture, not a calibrated '
                  'I/V curve. No leakage, 7406 input bias, IC power model, delay, clamps or brownout behavior. '
                  'Enable voltages 0/5 V represent release/drive; intermediate enables are not qualified.')
    return lines, report
