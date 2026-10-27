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
              mask=0, value=0, seed=0, initial=None, pattern='seed', bit=None):
        return json.loads(subprocess.check_output([str(ROOT/'build/pc1715-fault-probe'),
            str(self.rom), fault, bus, str(bias), str(decay), str(mask), str(value),
            str(seed), '200', str(bias if initial is None else initial), pattern]
            + ([] if bit is None else list(map(str, bit)))))

    def test_bit_write_modes(self):
        program=bytes([0x3e,0x5a,0x32,0,0x90,0x3a,0,0x90,0x76])
        self.rom.write_bytes(program+bytes(2048-len(program)))
        for mode, expected in [(0,0x5a),(1,0x52),(2,0x52),(3,0x5a),(4,0x52)]:
            self.assertEqual(self.probe(bit=[3,0,0,mode,0])['cpu_a'],expected)
        self.assertEqual(self.probe(bit=[3,0,0,0,1])['cpu_a'],0x52)

    def test_bit_address_alias_preserves_other_seven_bits(self):
        program=bytes([0x3e,0xda,0x32,1,0x90,0x3e,0xa5,0x32,0,0x90,
                       0x3a,1,0x90,0x76])
        self.rom.write_bytes(program+bytes(2048-len(program)))
        self.assertEqual(self.probe()['cpu_a'],0xda)
        self.assertEqual(self.probe(bit=[3,1,0,0,0])['cpu_a'],0xd2)

    def test_read_and_write_address_faults_are_distinct(self):
        for read_address, expected in [(0,[8,0,8]), (1,[0xda,0xd2,0xd2])]:
            program=bytes([0x3e,0xda,0x32,1,0x90,0x3a,read_address,0x90,0x76])
            self.rom.write_bytes(program+bytes(2048-len(program)))
            for mode,value in enumerate(expected):
                self.assertEqual(self.probe(bit=[3,1,0,0,0,mode])['cpu_a'],value)

    def test_independent_chip_retains_address_lost_in_ram_alias(self):
        # Common RAM A3 is stuck high, but D3 still sees the external low A3.
        args=dict(fault='decoder-ram-alias',mask=8,value=8,pattern='stripe:3:64:8')
        self.assertEqual(self.probe(**args,bit=[3,0,0,0,0,0])['fetches'][0]['cpu'],8)
        self.assertEqual(self.probe(**args,bit=[3,0,0,0,0,3])['fetches'][0]['cpu'],0)
        # A genuine upstream address-bus failure must still affect every chip.
        args=dict(fault='address-mask',mask=0x800,value=0x800,pattern='stripe:11:64:8')
        self.assertEqual(self.probe(**args,bit=[3,0,0,0,0,3])['fetches'][0]['cpu'],8)

    def test_independent_write_address_preserves_other_planes(self):
        source=Path(self.temp.name)/'write_test.c'
        source.write_text('#define main probe_main\n#include "'+str(ROOT/'verification/pc1715-faults/probe.c')+'"\n#undef main\n'+r'''
int main(void) {
  experiment x={0};
  pc1715_init(&x.board); x.original=x.board.cpu.bus;
  x.fault=DECODER_ALIAS; x.mask=0xffe0;
  x.bit_enabled=1; x.bit_index=3; x.bit_address_mode=3;
  write_memory(&x,0x8031,0xda);
  if (x.board.ram[0x11]!=0xd2 || x.board.ram[0x8031]!=8) return 1;
  write_memory(&x,0x11,0xa5);
  if (x.board.ram[0x11]!=0xa5 || x.board.ram[0x8031]!=8) return 2;
  if (ram_read(&x,0x11,0x8031)!=0xad) return 3;
  if (ram_read(&x,0x11,0x11)!=0xa5) return 4;
  return 0;
}
''')
        binary=Path(self.temp.name)/'write_test'
        objects=['build/machines/robotron1715/pc1715.o','build/common/cpu/z80.o',
                 'build/common/trace/trace.o']
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(source),
                        *[str(ROOT/p) for p in objects],'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)

    def test_regular_xor_startup_pattern(self):
        for address,value in enumerate([8,255,239,24]):
            program=bytes([0x3a,address,0x90,0x76])
            self.rom.write_bytes(program+bytes(2048-len(program)))
            result=self.probe(pattern='xorstripe:0:8:255:1:231')
            self.assertEqual(result['cpu_a'],value)
            self.assertEqual(result['fetches'][0]['read_data'],[address,0x90,value])

    def test_timed_write_fault_uses_clock_not_fetch_index(self):
        for address,expected in [(0,0),(1,8)]:
            program=bytes([0x3e,0,0x32,0,0x90,0x32,1,0x90,0x3a,address,0x90,0x76])
            self.rom.write_bytes(program+bytes(2048-len(program)))
            self.assertEqual(self.probe(bit=[3,0,0,1,0,0,20,3])['cpu_a'],expected)

    def test_io_read_data_is_counted_too(self):
        self.rom.write_bytes(bytes([0xdb,0x40,0x76])+bytes(2045))
        row=self.probe()['fetches'][0]
        self.assertEqual((row['reads'],row['read_data'],row['clocks']),(2,[0x40,255],11))

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
        with_reads=dict(observed,reads=1,read_data=[0])
        hardware['runs'][0]['fetches']=[with_reads]*3
        wrong_operand=compare(hardware,dict(fetches=[dict(with_reads,read_data=[8])]*4))[0]
        self.assertFalse(wrong_operand['reproduces_bounded_observation'])

    def test_bad_configuration_and_rom_rejected(self):
        cmd=[str(ROOT/'build/pc1715-fault-probe'),str(self.rom),
             'healthy','fixed','255','0','0','1','0','200']
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
        self.rom.write_bytes(b'short')
        cmd[7]='0'
        self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)


if __name__ == '__main__':
    unittest.main()
