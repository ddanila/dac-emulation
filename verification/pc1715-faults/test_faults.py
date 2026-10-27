"""Independent CPU/program expectations, plus hardware comparison guard tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from campaign import compare

ROOT = Path(__file__).resolve().parents[2]


class FaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rom = Path(self.temp.name)/'synthetic.bin'
        # LD HL,1234; LD A,5A; LD (9000),A; HALT.
        self.rom.write_bytes(bytes([0x21,0x34,0x12,0x3e,0x5a,0x32,0,0x90,0x76])+bytes(2039))

    def tearDown(self):
        self.temp.cleanup()

    def probe(self, fault='healthy', bus='fixed', bias=255, decay=0,
              mask=0, value=0, seed=0, initial=None, pattern='seed'):
        return json.loads(subprocess.check_output([str(ROOT/'build/pc1715-fault-probe'),
            str(self.rom), fault, bus, str(bias), str(decay), str(mask), str(value),
            str(seed), '200', str(bias if initial is None else initial), pattern]))

    def test_healthy_program_and_fetch_boundaries(self):
        rows = self.probe()['fetches']
        self.assertEqual([(r['address'],r['cpu'],r['clocks'],r['reads']) for r in rows[:3]],
                         [(0,0x21,10,2),(3,0x3e,7,1),(5,0x32,13,2)])
        self.assertTrue(all((r['ce'],r['oe'],r['driven'])==(0,0,1) for r in rows[:3]))

    def test_oe_failure_is_not_rom_disabled_overlay_fallback(self):
        rows = self.probe('rom-oe-high')['fetches']
        self.assertEqual([r['address'] for r in rows[:4]], [0,0x38,0x38,0x38])
        self.assertTrue(all((r['cpu'],r['oe'],r['ce'],r['driven'],r['clocks'])==
                            (255,1,0,0,11) for r in rows[:4]))
        # Returning underlying zero RAM would give NOPs, not these RSTs.

    def test_hold_follows_real_stack_write(self):
        rows = self.probe('rom-oe-high','hold')['fetches']
        self.assertEqual(rows[0]['cpu'],255)
        # RST at 0000 pushes return address 0001: low byte is the last write.
        self.assertEqual(rows[1]['address'],0x38)
        self.assertEqual((rows[1]['cpu'],rows[1]['clocks'],rows[1]['reads']), (1,10,2))

    def test_decay_is_time_based_not_capture_replay(self):
        rows = self.probe('rom-oe-high','decay',255,4,initial=8)['fetches']
        self.assertEqual([r['cpu'] for r in rows[:3]], [8,255,2])
        self.assertEqual([r['clocks'] for r in rows[:3]], [4,11,7])
        self.assertEqual([r['address'] for r in rows[:3]], [0,1,0x38])

    def test_address_fault_changes_decode_and_source(self):
        rows = self.probe('address-mask',mask=0x800,value=0x800)['fetches']
        self.assertEqual((rows[0]['cpu'],rows[0]['ce'],rows[0]['oe'],rows[0]['driven']), (0,0,1,1))

    def test_open_buffer_separates_cpu_from_connector(self):
        r = self.probe('data-buffer-open')['fetches'][0]
        self.assertEqual((r['cpu'],r['data'],r['clocks']), (0x21,255,10))

    def test_data_fault_does_not_disable_rom(self):
        r = self.probe('rom-data-mask',mask=0x29,value=8)['fetches'][0]
        self.assertEqual((r['cpu'],r['oe'],r['ce'],r['clocks']), (8,0,0,4))

    def test_random_ram_reproducible(self):
        self.assertEqual(self.probe('address-mask',mask=0x800,value=0x800,seed=42),
                         self.probe('address-mask',mask=0x800,value=0x800,seed=42))

    def test_aliased_stack_writes_change_instructions(self):
        rows=self.probe('decoder-ram-alias',mask=0xffc0,pattern='stripe:0:8:255')['fetches']
        # Three RSTs push 0002,003A,003A into RAM aliased to the low 64 bytes.
        # The third low-byte write replaces the FF at logical 0039 with 3A.
        self.assertEqual([r['cpu'] for r in rows[:10]], [8,255,8,255,8,255,8,0x3a,0,2])
        self.assertEqual(rows[7]['address'],0x39)
        self.assertEqual((rows[7]['clocks'],rows[7]['reads']), (13,3))
        self.assertTrue(all(r['ce']==0 and r['oe']==1 for r in rows[:10]))

    def test_high_address_fault_both_misses_rom_and_aliases_ram(self):
        rows=self.probe('address-mask',mask=0xffc0,value=0xffc0,
                        pattern='stripe:0:8:255')['fetches']
        self.assertEqual([r['cpu'] for r in rows[:8]], [8,255,8,255,8,255,8,0x3a])
        self.assertTrue(all(r['oe']==1 and r['ce']==0 and r['driven']==1 for r in rows[:8]))

    def test_comparison_rejects_bytes_only_and_short_runs(self):
        observed = dict(data=8,clocks=4,reads=0,ce=0,oe=1)
        hardware = dict(runs=[dict(name='test',fetches=[observed]*3)])
        mismatch = dict(observed,clocks=10)
        score = compare(hardware,dict(fetches=[mismatch]*4))[0]
        self.assertEqual(score['byte_prefix'],3)
        self.assertFalse(score['reproduces_bounded_observation'])
        short = compare(hardware,dict(fetches=[observed]*2))[0]
        self.assertFalse(short['reproduces_bounded_observation'])
        wrong_oe = compare(hardware,dict(fetches=[dict(observed,oe=0)]*4))[0]
        self.assertFalse(wrong_oe['reproduces_bounded_observation'])

    def test_bad_configuration_and_rom_rejected(self):
        cmd=[str(ROOT/'build/pc1715-fault-probe'),str(self.rom),
             'healthy','fixed','255','0','0','1','0','200']
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
        self.rom.write_bytes(b'short')
        cmd[7]='0'
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)


if __name__ == '__main__':
    unittest.main()
