"""Separate CPU operating checks from maximum ratings without granting allowances."""
import json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent

def classify_input(volts,supply,expected_high,limits=None,contract=None):
 if not all(math.isfinite(v) for v in (volts,supply)):raise ValueError('Nonfinite input observation')
 limits=limits or json.loads((HERE/'cpu_clock_limits.json').read_text())
 contract=contract or json.loads((HERE/'bus_device_contract.json').read_text())
 inp=limits['ordinaryInput'];op=limits['operatingConditions'];absolute=contract['devices']['U880']['absoluteInputRangeVolts']
 return {'logicThresholdPassed':volts>=inp['highMinimumVolts'] if expected_high else volts<=inp['lowMaximumVolts'],
         'staticInputRangePassed':inp['minimumVolts']<=volts<=supply+inp['maximumSupplyOffsetVolts'],
         'ratedSupplyPassed':op['supplyMinimumVolts']<=supply<=op['supplyMaximumVolts'],
         'withinAbsoluteInputRatings':absolute[0]<=volts<=absolute[1],
         'transientAllowanceEstablished':False,
         'interpretation':'Maximum-rating compliance does not establish operation, device safety, or permission to waive the static input range.'}

