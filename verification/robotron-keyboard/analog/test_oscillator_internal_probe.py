"""Guard internal observation column identity and gate-terminal mapping."""
import unittest
from oscillator_internal_probe import expand, read_op


class InternalProbeTests(unittest.TestCase):
    def test_external_and_hierarchical_nodes(self):
        gate = ('xa7_1', 'n_osc1', 'n_osc2')
        self.assertEqual(expand('v(a)', *gate), 'v(n_osc1)')
        self.assertEqual(expand('v(y)', *gate), 'v(n_osc2)')
        self.assertEqual(expand('v(vp)', *gate), 'v(n_p5v)')
        self.assertEqual(expand('@q.xgate.xsink.qcore[ic]', *gate),
                         '@q.xa7_1.xgate.xsink.qcore[ic]')

    def test_rejects_unusable_observations(self):
        signals = ['v(a)', '@q.xgate.qhigh[ic]']
        text = 'scale v(a) @q.xgate.qhigh[ic]\n0 1.1 -2e-6\n'
        self.assertEqual(read_op(text, signals)[signals[1]], -2e-6)
        for bad in [text.replace('1.1', 'nan'), text.replace('-2e-6', 'inf'),
                    text + '0 1.2 0\n', text.replace(' -2e-6', ''),
                    text.replace('v(a)', 'v(y)'), text.replace('0 1.1', 'nan 1.1')]:
            with self.assertRaises(ValueError):
                read_op(bad, signals)


if __name__ == '__main__':
    unittest.main()
