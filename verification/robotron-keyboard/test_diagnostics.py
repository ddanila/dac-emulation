#!/usr/bin/env python3
"""Fault injection checks for retained counterexamples and automatic VCD replay."""
import json,subprocess,tempfile,unittest,sys
from pathlib import Path
from diagnostics import first_difference,firmware_differences,waveform_window,run_bus,bus_differences
R=Path(__file__).resolve().parent
class DiagnosticsTests(unittest.TestCase):
 def test_custom_output_retains_service_wave_and_report(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'profile with spaces'
   subprocess.run([sys.executable,R/'run.py','--out',out],cwd=R.parents[1],
                  check=True,capture_output=True,text=True,timeout=60)
   self.assertTrue(json.loads((out/'report.json').read_text())['equivalent'])
   self.assertIn('$enddefinitions',(out/'service.vcd').read_text())
   self.assertIn('mismatches=0',(out/'service.log').read_text())

 def test_ordinal_values_keep_both_clocks(self):
  self.assertIsNone(first_difference([(10,'0')],[(12,'0')],'serial-bit'))
  d=first_difference([(10,'0'),(20,'1')],[(12,'0'),(22,'0')],'serial-bit')
  self.assertEqual((d['index'],d['cCycle'],d['hdlCycle'],d['cValue'],d['hdlValue']),(1,20,22,'1','0'))
  self.assertEqual(waveform_window([d],100),(0,54))
 def test_missing_events_and_sample_times_are_not_lost_by_zip(self):
  d=first_difference([(100,'1')],[],'raw-led-state')
  self.assertEqual(d['reason'],'missing-event');self.assertIsNone(d['hdlValue'])
  c={'BIT':[],'EDGE':[],'LED':[(100,'1')]};h={'BIT':[],'EDGE':[],'LED':[(101,'1')]}
  self.assertEqual(firmware_differences(c,h)[0]['signal'],'led-sample')
  self.assertEqual(waveform_window([],4600000),(0,1024))
 def test_injected_bus_faults_retain_first_signal_time_and_waveform(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);exe=out/'bus.vvp'
   subprocess.run(['iverilog','-g2012','-s','bus_tb','-o',exe,R/'chips.v',R/'generated/controller.v',R/'bus_tb.v'],check=True)
   vectors=out/'bus.txt'
   for name,vector in [('raw-led-state','0 0000 00 ff 3 0 0\n'),('read-data','0 0000 00 00 0 0 0\n'),('serial-output','1 0000 00 00 0 0 0\n')]:
    with self.subTest(signal=name):
     vectors.write_text(vector);(out/'bus.vcd').unlink(missing_ok=True)
     result=run_bus(['vvp',exe,'+vectors='+str(vectors)],out,R.parents[1])
     self.assertNotEqual(result.returncode,0)
     failures=bus_differences(result.stdout)
     self.assertEqual(failures[0]['signal'],name);self.assertEqual(failures[0]['vector'],0)
     self.assertEqual(failures[0]['simulationTimeNs'],10)
     wave=(out/'bus.vcd').read_text();self.assertIn('$enddefinitions',wave);self.assertIn('#10000',wave)
     self.assertIn('board/emulator mismatch',(out/'bus-wave.log').read_text())
   vectors.write_text('0 0000 00 ff 0 0 0\n');(out/'bus.vcd').unlink()
   self.assertEqual(run_bus(['vvp',exe,'+vectors='+str(vectors)],out,R.parents[1]).returncode,0)
   self.assertFalse((out/'bus.vcd').exists())
 def test_firmware_wave_replay_stops_at_requested_cycle(self):
  for timed,scale in ((False,1),(True,100)):
   with self.subTest(timed=timed),tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp);exe=out/'firmware.vvp';rom=out/'rom.hex';wave=out/'firmware.vcd'
    rom.write_text('00\n'*2048)
    timing=['-Pfirmware_tb.ROM_READ_ENVELOPE=1','-Pfirmware_tb.CLOCK_HALF_NS=500',R/'analog/eprom2716.v'] if timed else []
    subprocess.run(['iverilog','-g2012','-s','firmware_tb','-o',exe,*timing,*sorted((R.parents[1]/'third_party/cpu/tv80').glob('*.v')),R/'chips.v',R/'generated/controller.v',R/'firmware_tb.v'],check=True)
    subprocess.run(['vvp',exe,'+rom='+str(rom),'+wave='+str(wave),'+wave_start=10','+wave_end=20'],check=True,capture_output=True,timeout=10)
    times=[int(line[1:])for line in wave.read_text().splitlines()if line.startswith('#')]
    self.assertIn(260000*scale,times);self.assertEqual(max(times),360000*scale)
 def test_floating_input_fixture_preserves_driven_reads(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);exe=out/'probe.vvp';rom=out/'rom.hex'
   rom.write_text('00\n'*2048)
   (out/'probe.v').write_text("""`timescale 1ns/1ps
module probe;
 firmware_tb #(.FLOATING_IO_OVERRIDE(1),.FLOATING_IO_VALUE(8'hxx)) dut();
 initial begin
  force dut.address=0; force dut.mreq_n=0;
  force dut.iorq_n=1; force dut.rd_n=0; force dut.read_data=8'ha5;
  #1; if(dut.di!==8'h00)$fatal(1,"ROM read overridden");
  force dut.mreq_n=1; force dut.iorq_n=0; force dut.address=16'h8000;
  #1; if(dut.di!==8'ha5)$fatal(1,"Enabled latch read overridden");
  force dut.address=0;
  #1; if(dut.di!==8'hxx)$fatal(1,"Released read did not preserve unknown");
  force dut.rd_n=1;
  #1; if(dut.di!==8'ha5)$fatal(1,"Non-read overridden");
  $display("FLOATING_INPUT_BOUNDARY_PASS");$finish;
 end
endmodule
""")
   subprocess.run(['iverilog','-g2012','-s','probe','-o',exe,*sorted((R.parents[1]/'third_party/cpu/tv80').glob('*.v')),R/'chips.v',R/'generated/controller.v',R/'firmware_tb.v',out/'probe.v'],check=True)
   result=subprocess.run(['vvp',exe,'+rom='+str(rom)],check=True,capture_output=True,text=True,timeout=10)
   self.assertIn('FLOATING_INPUT_BOUNDARY_PASS',result.stdout)
if __name__=='__main__':unittest.main()
