"""Counterexamples for ordinal logical comparisons; timestamps stay independent."""
import json,subprocess
from itertools import zip_longest

def first_difference(c,hdl,signal,compare_cycles=False):
 for index,(left,right) in enumerate(zip_longest(c,hdl)):
  if left is None or right is None or left[1]!=right[1] or (compare_cycles and left[0]!=right[0]):
   return {'signal':signal,'index':index,'cCycle':left[0] if left else None,
           'hdlCycle':right[0] if right else None,'cValue':left[1] if left else None,
           'hdlValue':right[1] if right else None,
           'reason':'missing-event' if left is None or right is None else 'value-or-sample-time'}
 return None

def firmware_differences(c,hdl):
 return [d for d in [first_difference(c['BIT'],hdl['BIT'],'serial-bit'),
                     first_difference(c['EDGE'],hdl['EDGE'],'raw-led-state'),
                     first_difference(c['LED'],hdl['LED'],'led-sample',True)] if d]

def waveform_window(differences,cycles):
 times=[d[k] for d in differences for k in ['cCycle','hdlCycle'] if d[k] is not None]
 # Preserve both clocks for the earliest divergence; don't align away offsets.
 if not times:return 0,min(cycles,1024)
 earliest=min(differences,key=lambda d:min(d[k] for k in ['cCycle','hdlCycle'] if d[k] is not None))
 times=[earliest[k] for k in ['cCycle','hdlCycle'] if earliest[k] is not None]
 return max(0,min(times)-32),min(cycles,max(times)+32)

def run_bus(args,out,cwd,wave=False):
 result=subprocess.run([str(x)for x in args],cwd=cwd,text=True,capture_output=True,timeout=30)
 (out/'bus.log').write_text(result.stdout+result.stderr)
 if result.returncode and not wave:
  replay=subprocess.run([str(x)for x in args]+['+wave='+str(out/'bus.vcd')],cwd=cwd,text=True,capture_output=True,timeout=30)
  (out/'bus-wave.log').write_text(replay.stdout+replay.stderr)
 return result

def bus_differences(stdout):
 return [json.loads(line[5:])for line in stdout.splitlines()if line.startswith('FAIL ')]
