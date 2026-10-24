import unittest
from live_raw_output import raw_deck


class LiveRawOutputTests(unittest.TestCase):
    def test_changes_only_output_commands(self):
        deck='title\n.save v(a) i(V1)\n.tran 1n 1m\n.control\nset numdgt=17\nrun\nwrdata one.txt v(a)\nwrdata two.txt i(V1)\nquit\n.endc\n.end\n'
        changed,writers=raw_deck(deck)
        self.assertEqual(writers,[('one.txt','v(a)'),('two.txt','i(V1)')])
        expected=deck.replace('run\n','set filetype=binary\nrun waveform.raw\n').replace('wrdata one.txt v(a)\n','').replace('wrdata two.txt i(V1)\n','')
        self.assertEqual(changed,expected)

    def test_rejects_ambiguous_or_modified_control_flow(self):
        deck='title\n.control\nrun\nwrdata trace.txt v(a)\nquit\n.endc\n'
        for command in ('run','stop when time=1n','resume','set filetype=ascii','linearize','let a=1'):
            with self.subTest(command=command),self.assertRaises(ValueError):
                raw_deck(deck.replace('run\n',command+'\nrun\n'))


if __name__=='__main__':
    unittest.main()
