import os,subprocess,json,hashlib,sys
from pathlib import Path
base=Path("/opt/homebrew/Cellar/icarus-verilog/13.0/lib/ivl")
fixture=Path("verification/robotron-keyboard/firmware_tb.v").read_text().replace("firmware_tb","probe")
rom=Path(sys.argv[1]).read_bytes()
fixture=fixture.replace('if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");$readmemh(file,rom);', "\n".join("rom[%d]=8'h%02x;" % (i,v) for i,v in enumerate(rom)))
bench=Path("verification/robotron-keyboard/chips.v").read_text()+"\n"+Path("verification/robotron-keyboard/generated/controller.v").read_text()+"\n"+fixture

sources=sorted(Path("third_party/cpu/tv80").glob("*.v"))
preprocessed=subprocess.run([str(base/"ivlpp"),"-L",*map(str,sources),"/dev/stdin"],input=bench.encode(),capture_output=True,timeout=20)
preprocessed.check_returncode()
config=f"basedir:{base}\nmodule:{base}/system.vpi\ngeneration:2012\nroot:probe\nfunctor:cprop\nfunctor:nodangle\nflag:DLL=vvp.tgt\nout:/dev/stdout\niwidth:32\nwidthcap:65536\n".encode()
read,write=os.pipe();os.write(write,config);os.close(write)
try:
 compiled=subprocess.run([str(base/"ivl"),"-C",f"/dev/fd/{read}","/dev/stdin"],input=preprocessed.stdout,capture_output=True,pass_fds=(read,),timeout=20)
finally: os.close(read)
if compiled.stderr: print(compiled.stderr.decode())
compiled.check_returncode()
run=subprocess.run(["vvp","/dev/stdin"],input=compiled.stdout,capture_output=True,timeout=300)
run.check_returncode()
report={"scope":"Full S600 digital firmware fixture with generated read-phase candidate; not electrical qualification","romSha256":hashlib.sha256(rom).hexdigest(),
"benchSha256":hashlib.sha256(bench.encode()).hexdigest(),"compiledSha256":hashlib.sha256(compiled.stdout).hexdigest(),
"sources":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
"tools":{str(base/p):hashlib.sha256((base/p).read_bytes()).hexdigest() for p in ("ivl","ivlpp","vvp.tgt","system.vpi")},
"logSha256":hashlib.sha256(run.stdout).hexdigest(),
"events":{kind:{"count":len(lines),"sha256":hashlib.sha256(("\n".join(lines)+"\n").encode()).hexdigest(),"first":lines[:2],"last":lines[-2:]} for kind in ("BIT","LED","EDGE") for lines in [[line for line in run.stdout.decode().splitlines() if line.startswith(kind+" ")]]},
"completed": "finish called at 46000160000" in run.stdout.decode(),
"qualified":False}
print(json.dumps(report,indent=2))
