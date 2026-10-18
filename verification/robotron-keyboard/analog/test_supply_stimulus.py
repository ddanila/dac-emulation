import json
from pathlib import Path
import tempfile
import unittest
from supply_stimulus import load, source


class SupplyTests(unittest.TestCase):
    def test_shipped_supply_stimuli(self):
        for path in (Path(__file__).parent/'supply-stimuli').glob('*.json'):
            with self.subTest(path=path):
                load(path, .127)

    def test_brownout_roundtrip(self):
        data = {'pointsSecondsVolts': [[0, 0], [.001, 5], [.1, 5], [.11, 2], [.12, 5], [.127, 5]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'supply.json'
            path.write_text(json.dumps(data))
            self.assertEqual(load(path, .127), data)
        values = list(map(float, source(data, 1)[4:-1].split()))
        self.assertEqual(values, [v for point in data['pointsSecondsVolts'] for v in point])
        self.assertEqual(source(None, 1), 'PWL(0 0 1u 5)')

    def test_invalid_or_incomplete_stimulus(self):
        bad = [[], [[0,0]], [[0,5],[.127,5]], [[0,0],[0,5],[.127,5]],
               [[0,0],[.13,5],[.127,5]], [[0,0],[.126,5]],
               [[0,0],[.128,5]], [[0,0],[.127,-1]],
               [[0,0],[.127,float('nan')]], [[0,0],[.127,True]],
               [[0,0],[.127,'5']], [[0,0],[.127,5,1]]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'supply.json'
            for points in bad:
                with self.subTest(points=points):
                    path.write_text(json.dumps({'pointsSecondsVolts': points}))
                    with self.assertRaises(ValueError):
                        load(path, .127)


if __name__ == '__main__':
    unittest.main()
