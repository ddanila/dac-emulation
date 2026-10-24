import unittest
from scenario_capture import endpoint_ns, validate_stimulus
from io_scenario import contact_source, reset_source


class ScenarioCaptureTests(unittest.TestCase):
    def test_stimulus_must_match_contacts_reset_and_clock(self):
        scenario={'contacts':[{'cycle':4000,'index':61,'closed':True}],'resets':[]}
        deck='\n'.join(f'Vcontact{i} contact{i} 0 '+contact_source(scenario,i) for i in range(104))
        deck+='\nVfixture_reset fixture_reset 0 '+reset_source(scenario)
        deck+='\nVfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)\n'
        validate_stimulus(deck,scenario)
        for changed in (deck.replace('5000001n 5','5000001n 0'),
                        deck.replace('499n 1u','499n 2u'),
                        deck.replace('1000001n 5','1000001n 0'),
                        deck+'Vcontact0 contact0 0 0\n',deck+'alter Vcontact61=0\n'):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                validate_stimulus(changed,scenario)

    def test_full_repeat_endpoint_is_derived_from_cycles_and_reset(self):
        self.assertEqual(endpoint_ns('.tran 25n 1601000000n\n',{'cycles':1600000}),1601000000)
        self.assertEqual(endpoint_ns('.tran 25n 1.601e9n\n',{'cycles':1600000},1601000000),1601000000)

    def test_rejects_shortening_extension_skipped_start_and_halt(self):
        for deck,override in [('.tran 25n 1006000n\n',None),
                              ('.tran 25n 1601000001n\n',None),
                              ('.tran 25n 1601000000n\n',1006000),
                              ('.tran 25n 1601000000n\n',float('nan')),
                              ('.tran 25n 1601000000n 1000000n\n',None),
                              ('.tran 25n 1601000000n\nstop when time = 1m\n',None),
                              ('.tran 25n 1601000000n\n.tran 25n 1601000000n\n',None)]:
            with self.subTest(deck=deck,override=override),self.assertRaises(ValueError):
                endpoint_ns(deck,{'cycles':1600000},override)


if __name__=='__main__':unittest.main()
