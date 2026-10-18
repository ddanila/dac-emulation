#!/usr/bin/env python3
"""Service boundaries must not hide missing electrical models or new components."""
import unittest

from circuit import load
from cpu_control import wiring as cpu_wiring
from logic_control import wiring as logic_wiring
from matrix import matrix_circuit
from model_coverage import classify_service
from output_circuit import output_circuit


class ServiceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.components, _ = load()
        _, matrix = matrix_circuit(self.components)
        _, outputs = output_circuit(self.components)
        self.models = {**matrix['models'], **outputs['models']}

    def test_options_have_explicit_domains(self):
        for cpu in (False, True):
            for logic in (False, True):
                with self.subTest(cpu=cpu, logic=logic):
                    models = dict(self.models)
                    if cpu:
                        models.update(cpu_wiring(self.components)[1])
                    if logic:
                        models.update(logic_wiring(self.components)[1])
                    result = classify_service(self.components, models, cpu, logic)['components']
                    self.assertEqual(set(result), set(self.components))
                    for ref in ('A7', 'C6', 'V4.9', 'BR1', 'BR2'):
                        self.assertEqual(result[ref]['domain'], 'boundary')
                    for ref in ('R1', 'V4.1', 'C5.1', 'L1.1'):
                        self.assertEqual(result[ref]['domain'], 'electrical')
                    for enabled, refs in ((cpu, ('R6.4', 'R6.5')), (logic, ('R6.3', 'R6.6', 'R9.9'))):
                        for ref in refs:
                            self.assertEqual(result[ref]['domain'], 'electrical' if enabled else 'digital-or-interface')
                    self.assertIn('externally supplied digital service clock/reset', result['A5']['model'])

    def test_unclassified_or_missing_models_fail(self):
        changed = {**self.components, 'RNEW': {'type': 'R', 'pins': {}}}
        with self.assertRaisesRegex(ValueError, 'Unclassified board component: RNEW'):
            classify_service(changed, self.models)
        missing = dict(self.models)
        del missing['R1']
        with self.assertRaisesRegex(ValueError, 'Unclassified board component: R1'):
            classify_service(self.components, missing)
        with self.assertRaisesRegex(ValueError, 'absent from schematic'):
            classify_service(self.components, {**self.models, 'RPHANTOM': 'resistor'})

    def test_exclusion_conflicts_and_control_option_mismatch_fail(self):
        with self.assertRaisesRegex(ValueError, 'both an electrical model'):
            classify_service(self.components, {**self.models, 'C6': 'capacitor'})
        with self.assertRaisesRegex(ValueError, 'enabled service options'):
            classify_service(self.components, self.models, cpu_pullups=True)
        with self.assertRaisesRegex(ValueError, 'enabled service options'):
            classify_service(self.components, {**self.models, **logic_wiring(self.components)[1]})


if __name__ == '__main__':
    unittest.main()
