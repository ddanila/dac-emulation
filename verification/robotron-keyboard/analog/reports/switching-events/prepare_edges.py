from pathlib import Path
import shutil,subprocess,json,hashlib
base=Path('build/keyboard-controller-analog');old=base/'input-barrier-v2-coarse';out=base/'live-edge-prepared';out.mkdir(exist_ok=False)
for n in ('s600.hex','io.cir'):shutil.copyfile(base/'bus-switch-controls/after-tight'/n,out/n)
s=(old/'controller_analog.v').read_text();needle='   $display("BUS_SAMPLE';assert s.count(needle)==1;s=s.replace(needle,'   $display("BUS_EDGE_PS %0.0f",$realtime*1000.0);\n'+needle);(out/'controller_analog.v').write_text(s)
hdl=[*sorted((old/'qualified-cpu').glob('*.v')),Path('third_party/cpu/tv80/tv80_alu.v'),Path('third_party/cpu/tv80/tv80_reg.v'),Path('verification/robotron-keyboard/chips.v'),Path('verification/robotron-keyboard/generated/controller.v'),out/'controller_analog.v']
command=['iverilog','-g2012','-DTV80_REFRESH','-s','firmware_io_electrical_bus','-o',str(out/'io.vvp'),*map(str,hdl)];subprocess.run(command,check=True)
(out/'build.json').write_text(json.dumps({'command':command,'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in hdl}},indent=2)+'\n')
