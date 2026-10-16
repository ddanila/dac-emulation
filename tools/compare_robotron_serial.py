#!/usr/bin/env python3
"""Optional independent S600 serial data/error comparison against MAME."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--mame', default='mame')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.media = args.media.resolve()
    subprocess.run(['make', 'build/robotron-serial-comparison'], cwd=ROOT, check=True)
    actual = subprocess.check_output([ROOT / 'build/robotron-serial-comparison', args.media / 's600.bin'], text=True).splitlines()
    with tempfile.TemporaryDirectory(prefix='dac-serial-reference-') as directory:
        tmp = Path(directory)
        (tmp / 'rt1715w').mkdir()
        (tmp / 'rt1715w/s550.bin').write_bytes(bytes([0x76]) + bytes(2047))
        for source, dest in [('cas.bin', '287.bin'), ('s600.bin', 's600.ic8')]:
            (tmp / 'rt1715w' / dest).write_bytes((args.media / source).read_bytes())
        script = r'''
local m=manager.machine
local ports=m.devices[':maincpu'].spaces['io']
local key=nil
for _,field in pairs(m.ioport.ports[':row_70'].fields) do
 if field.mask==32 then key=field end
end
assert(key)
local output=assert(io.open('serial.txt','w'))
local function reg(n,v) ports:write_u8(14,n);ports:write_u8(14,v) end
local frame=0
emu.register_frame_done(function()
 frame=frame+1
 for test=0,2 do
  local start=100+test*60
  if frame==start then
   ports:write_u8(14,0x18);reg(3,test==1 and 0x41 or 0xc1);reg(4,test==1 and 7 or 4)
   key:set_value(1)
  end
  if frame==start+10 then key:set_value(0) end
  if test==2 and frame==start+20 then key:set_value(1) end
  if test==2 and frame==start+30 then key:set_value(0) end
  if frame==start+(test==2 and 40 or 20) then
   local count=0
   while (ports:read_u8(14)&1)~=0 and count<8 do
    count=count+1;ports:write_u8(14,1)
    local status=ports:read_u8(14);local value=ports:read_u8(12)
    output:write(string.format('RX %d %02x %02x\n',test,value,status&0x70))
   end
   if test==2 then output:close();m:exit() end
  end
 end
end)
'''
        (tmp / 'probe.lua').write_text(script)
        run = subprocess.run([args.mame, 'rt1715w', '-rompath', str(tmp), '-video', 'none', '-sound', 'none',
            '-nothrottle', '-skip_gameinfo', '-autoboot_script', str(tmp / 'probe.lua'), '-seconds_to_run', '8'],
            cwd=tmp, env={**os.environ, 'SDL_VIDEODRIVER': 'dummy'}, capture_output=True, text=True, timeout=30)
        if run.returncode or not (tmp / 'serial.txt').exists():
            raise RuntimeError(run.stdout + run.stderr)
        reference = (tmp / 'serial.txt').read_text().splitlines()
    report = {'passed': actual == reference and len(actual) == 7,
              'reference': subprocess.check_output([args.mame, '-version'], text=True).strip(),
              'core': subprocess.check_output(['git', 'describe', '--always', '--dirty', '--abbrev=40', '--exclude=*'], cwd=ROOT, text=True).strip(),
              'firmwareSha256': hashlib.sha256((args.media / 's600.bin').read_bytes()).hexdigest(),
              'scope': ['S600 A packet through real keyboard CPU and SIO A', '8N1 reception', 'S600 FIFO overrun replaces third character',
                        'deliberate 7E1 receiver mismatch: per-character parity status'],
              'dac': actual, 'mame': reference,
              'limitations': ['Stable bytes/status, not bit-edge timing or physical hardware.',
                              'No V.24 noise, synchronous modes or exhaustive error combinations.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
