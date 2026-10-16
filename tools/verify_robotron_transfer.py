#!/usr/bin/env python3
"""Optional bounded TOS/M guest qualification using local historical media."""
import ctypes as C, pathlib, argparse, json, hashlib
p=argparse.ArgumentParser();p.add_argument('--media',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];lib=C.CDLL(str(root/'build/libdac-runtime.so'))
def bind(n,args,result=C.c_int):
 f=getattr(lib,n);f.argtypes=args;f.restype=result;return f
ptr=C.c_void_p;u=C.c_uint
create=bind('dac_create',[u],ptr);load=bind('dac_load',[ptr,u,ptr,C.c_size_t]);mount=bind('dac_mount_unit',[ptr,u,ptr,C.c_size_t,C.c_int]);power=bind('dac_power',[ptr,C.c_int]);run=bind('dac_run',[ptr,u],u);key=bind('dac_key',[ptr,u,C.c_int]);send=bind('dac_serial_send',[ptr,u]);signals=bind('dac_serial_signals',[ptr,u]);size=bind('dac_serial_size',[ptr],u);data=bind('dac_serial_data',[ptr],ptr);diskdata=bind('dac_disk_data',[ptr],ptr)
disk=bytearray((a.media/'tosm10.img').read_bytes());program=(root/'examples/robotron-v24/DACRX.COM').read_bytes()
# Add an original COM to a temporary copy, preserving all original allocations.
for filename in ['DACRX','DACTX']:
 program=(root/f'examples/robotron-v24/{filename}.COM').read_bytes()
 entries=[disk[20480+i*32:20480+(i+1)*32] for i in range(128)]
 used={0,1}
 for e in entries:
  if e[0]!=0xe5:used.update(int.from_bytes(e[j:j+2],'little') for j in range(16,32,2))
 block=next(i for i in range(2,390) if i not in used);index=next(i for i,e in enumerate(entries) if e[0]==0xe5)
 e=bytearray(32);e[1:12]=(filename.ljust(8)+'COM').encode();e[15]=(len(program)+127)//128;e[16:18]=block.to_bytes(2,'little')
 disk[20480+index*32:20480+(index+1)*32]=e;disk[20480+block*2048:20480+block*2048+len(program)]=program
s=create(2)
for slot,name in [(0,'s550.bin'),(1,'cas.bin')]:
 b=(a.media/name).read_bytes();assert load(s,slot,b,len(b))==0
assert mount(s,0,bytes(disk),len(disk),1)==0;assert power(s,1)==0;assert signals(s,3)==0
def clocks(n):
 while n:step=min(n,100000);assert run(s,step)==step;n-=step
def output():return C.string_at(data(s),size(s))
clocks(100_000_000)
for ch in b'DACRX RECEIVED.BIN\r':assert key(s,ch,1)==0;clocks(500_000)
clocks(10_000_000)
seen=len(output());assert seen and output()[-1]==0x15,output()
def exchange(packet,want):
 global seen
 for b in packet:assert send(s,b)==0
 for _ in range(1200):
  clocks(100000);out=output()
  if len(out)>seen:
   replies=out[seen:];seen=len(out)
   if want in replies:return
 raise AssertionError(('reply',want,output()[-20:]))
payload=bytes((i*37+9)&255 for i in range(256));retries=0
for n in [1,2]:
 b=payload[(n-1)*128:n*128];frame=bytes([1,n,255-n])+b+bytes([sum(b)&255])
 if n==1:
  bad=frame[:-1]+bytes([frame[-1]^1]);exchange(bad,0x15);retries+=1
 exchange(frame,6)
 if n==1:exchange(frame,6) # duplicate acknowledged, not written twice
exchange(bytes([4]),6);clocks(5_000_000)
result=C.string_at(diskdata(s),819200);found=[]
for i in range(128):
 e=result[20480+i*32:20480+(i+1)*32]
 if e[0]==0 and e[1:12]==b'RECEIVEDBIN':found.append(e)
assert len(found)==1,found
e=found[0];actual=b''.join(result[20480+int.from_bytes(e[j:j+2],'little')*2048:20480+int.from_bytes(e[j:j+2],'little')*2048+2048] for j in range(16,32,2) if int.from_bytes(e[j:j+2],'little'))[:e[15]*128]
assert actual==payload,(len(actual),actual[:20])
# Send the just-created binary back through the real guest program.
for ch in b'DACTX RECEIVED.BIN\r':assert key(s,ch,1)==0;clocks(500_000)
clocks(10_000_000);seen=len(output());assert send(s,21)==0
returned=bytearray();packet=bytearray();finished=False
for _ in range(4000):
 clocks(100000);out=output();fresh=out[seen:];seen=len(out)
 for b in fresh:
  if not packet and b==4:assert send(s,6)==0;finished=True;break
  if not packet:assert b==1,('header',b)
  packet.append(b)
  if len(packet)==132:
   assert packet[1]^packet[2]==255
   assert sum(packet[3:131])&255==packet[131]
   returned.extend(packet[3:131]);packet.clear();assert send(s,6)==0
 if finished:break
assert finished and bytes(returned)==payload,('reverse transfer',len(returned),finished)
report={'passed':True,'guest':'TOS/M 1.0','protocol':'XMODEM-128 checksum','bytes':len(actual),'sha256':hashlib.sha256(actual).hexdigest(),'checks':['guest COM loaded through filesystem','bad checksum NAK and retry','duplicate block ACK without duplicate write','EOT ACK after BDOS close','guest-created file byte equality','DACTX guest-to-host binary equality'],'limitations':['128-byte record length; final block padded','No physical UART qualification','Receiver timeout re-NAKs; explicit cancellation required to exit waiting receiver']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
