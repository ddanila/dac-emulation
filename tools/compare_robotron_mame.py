#!/usr/bin/env python3
"""Bounded original-ROM differential probe. Requires optional MAME rt1715w."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, tempfile
p=argparse.ArgumentParser()
p.add_argument('--media',type=pathlib.Path,required=True,help='directory containing cas.bin and s600.bin')
p.add_argument('--mame',default='mame');p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1]
def run(cmd,**kwargs):
    return subprocess.run(cmd,check=True,text=True,capture_output=True,timeout=45,**kwargs).stdout
def digest(data): return hashlib.sha256(data).hexdigest()
code=bytearray([0xf3,0x31,0xff,0x7f])
def out(port,value): code.extend([0x3e,value,0xd3,port])
def store(address,value): code.extend([0x3e,value,0x32,address&255,address>>8])
store(0x4000,0x5a);store(0x4001,0xa5)
# Two-byte memory DMA, then screen character RAM and an IM2 timer interrupt.
for v in [0xc3,0x7d,0,0x40,1,0,0x14,0x10,0x8d,0,0x50,0x82,0xcf,0xb3,0x87]: out(0,v)
store(0x3000,ord('D'));store(0x3001,ord('A'));store(0x3002,0x91)
store(0x6082,0x20);store(0x6083,1)
store(0x6080,0);store(0x6081,1)
code.extend([0x3e,0x60,0xed,0x47,0xed,0x5e]) # I=60, IM2
out(4,0x80);out(4,0x87);out(4,200);out(5,0x87);out(5,200)
code.extend([0xfb,0x76,0x18,0xfd])
rom=code+bytes(2048-len(code))
rom[0x100:0x10e]=bytes([0xf3,0x3e,0x77,0x32,0,0x60,0x3e,3,0xd3,4,0xfb,0xed,0x4d,0])
rom[0x120:0x12e]=bytes([0xf3,0x3a,0,0x60,0x32,3,0x60,0x3e,3,0xd3,5,0xfb,0xed,0x4d])
run(['make','build/robotron-comparison'],cwd=root)
with tempfile.TemporaryDirectory(prefix='dac-reference-') as tmp:
    tmp=pathlib.Path(tmp);media=tmp/'rt1715w';media.mkdir()
    (media/'s550.bin').write_bytes(rom)
    for src,dst in [('cas.bin','287.bin'),('s600.bin','s600.ic8')]:shutil.copyfile(a.media/src,media/dst)
    output=tmp/'reference.txt';script=tmp/'probe.lua'
    script.write_text('''local m=manager.machine
local p=m.devices[':maincpu'].spaces['program']
local trace={}
local tap=m.devices[':maincpu'].spaces['io']:install_write_tap(0,255,'dac-probe',function(a,v) table.insert(trace,string.format('IO %02x %02x',a&255,v)) end)
local frames=0
emu.register_frame_done(function()
 frames=frames+1;if frames~=5 then return end
 local f=io.open('''+json.dumps(str(output))+''','w')
 for _,a in ipairs({0x4000,0x4001,0x5000,0x5001,0x6000,0x3000,0x3001,0x3002,0x6003}) do f:write(string.format('%04x %02x\\n',a,p:read_u8(a))) end
 local io=m.devices[':maincpu'].spaces['io']
 for b=1,7 do io:write_u8(0x24,b*17);p:write_u8(0x7000,0xa0+b) end
 for b=0,7 do io:write_u8(0x24,b);f:write(string.format('BANK %d %02x\\n',b,p:read_u8(0x7000))) end
 io:write_u8(0x24,0)
 io:write_u8(0x1d,0xff);f:write(string.format('FDC %02x\\n',io:read_u8(0x1d)))
 io:write_u8(0x0f,0x18);io:write_u8(0x0f,1);f:write(string.format('SIO-RR1 %02x\\n',io:read_u8(0x0f)))
 for _,v in ipairs(trace)do f:write(v..'\\n')end
 f:close();m:exit()
end)
''')
    log=run([a.mame,'rt1715w','-rompath',str(tmp),'-video','none','-sound','none','-nothrottle','-skip_gameinfo','-autoboot_script',str(script),'-seconds_to_run','2'],env={**os.environ,'SDL_VIDEODRIVER':'dummy'},cwd=tmp)
    reference=output.read_text().splitlines()
    actual=run([str(root/'build/robotron-comparison'),str(media/'s550.bin'),str(media/'287.bin'),str(media/'s600.ic8')]).splitlines()
report={'reference':run([a.mame,'-version']).strip(),'machine':'rt1715w','core':run(['git','describe','--always','--dirty','--abbrev=40','--exclude=*'],cwd=root).strip(),'diagnosticSha256':digest(rom),'firmware':{name:digest((a.media/name).read_bytes()) for name in ['cas.bin','s600.bin']},'scope':['CPU memory writes','two-byte memory DMA','ordered I/O writes','CTC interrupt with IM2 handler and RETI','display character and attribute RAM (not scanout pixels)','two pending CTC channels with ordered IM2 handlers','PROM bank write/read alias mapping','FDC invalid-command result','SIO reset RR1'],'boundaries':['Original diagnostic replaces S550; its MAME checksum warning is expected.','Checks stable outcomes after bounded execution, not clock equality.','Agreement is not physical-hardware validation.','External serial line error injection is covered by native diagnostics, not this MAME harness.'],'passed':actual==reference,'dac':actual,'mame':reference}
report['firstDifference']=next(({'index':i,'dac':actual[i] if i<len(actual) else None,'mame':reference[i] if i<len(reference) else None} for i in range(max(len(actual),len(reference))) if i>=len(actual) or i>=len(reference) or actual[i]!=reference[i]),None)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'output':str(a.output)}))
raise SystemExit(0 if report['passed'] else 1)
