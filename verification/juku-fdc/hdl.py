#!/usr/bin/env python3
"""Read-only use of the sibling reproduction; all output is isolated."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def main():
    p=argparse.ArgumentParser()
    for name in ('cosim','rom','disk','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--full-board',action='store_true')
    a=p.parse_args()
    for name in ('cosim','rom','disk','output'):setattr(a,name,getattr(a,name).resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'ref').symlink_to(a.cosim/'ref',target_is_directory=True)
    (a.output/'hdl/sim').mkdir(parents=True)
    here=Path(__file__).resolve().parent
    devices=str(a.cosim/'hdl/devices.v');cpu=str(a.cosim/'hdl/vendor/vm80a.v')
    results={}
    def run(name,cmd,marker=None,timeout=240):
        try:
            r=subprocess.run(cmd,cwd=a.output,capture_output=True,text=True,timeout=timeout)
            log=r.stdout+r.stderr;(a.output/(name+'.log')).write_text(log)
            results[name]={'exit_code':r.returncode,'command':cmd,
                'log_sha256':hashlib.sha256(log.encode()).hexdigest()}
            if r.returncode or (marker and marker not in log):raise RuntimeError(name+' failed; see log')
            return log
        except subprocess.TimeoutExpired:
            results[name]={'timeout_seconds':timeout};raise
    try:
        for name,top,source,flags,marker in [
            ('bus','issue25_bus_wait',here/'bus_wait_tb.sv',[],'VM80A PROM READY: PASS'),
            ('controller','fdc_1793_tb',a.cosim/'hdl/sim/fdc_1793_tb.v',
             ['-DFDC_BYTE_TIMING','-DFDC_TYPE_I_TIMING','-DFDC_TYPE_II_III_TIMING'],'FDC-1793: PASS')]:
            exe=str(a.output/name)
            run(name+'-build',['iverilog','-g2012',*flags,'-s',top,'-o',exe,cpu,devices,str(source)])
            run(name,['vvp',exe],marker)
        obj=a.output/'ag3'
        run('ag3-build',['verilator','--binary','--timing','-Wno-fatal','--top-module','ag3_oneshot_tb',
                        '-Mdir',str(obj),devices,str(a.cosim/'hdl/sim/ag3_oneshot_tb.v')])
        run('ag3',[str(obj/'Vag3_oneshot_tb')],'AG3-ONESHOT: PASS')
        if a.full_board:
            obj=a.output/'board-build'
            run('board-build',['verilator','--binary','--timing','-Wno-fatal','--top-module','issue25_board_trace',
                '-Mdir',str(obj),cpu,devices,str(a.cosim/'hdl/juku_top.v'),
                str(a.cosim/'hdl/sim/juku_top_tb.v'),str(here/'board_trace.sv')])
            rom=a.output/'rom.hex';rom.write_text('\n'.join(f'{b:02x}' for b in a.rom.read_bytes())+'\n')
            log=run('board',[str(obj/'Vissue25_board_trace'),f'+rom={rom}',f'+disk={a.disk}',
                '+disk_heads=2','+frameirq=0','+frame_mcyc=50761','+framephase=49891','+ekdoskeys=1',
                '+keyat=42000','+khold=900000','+kgap=900000','+tracefdc=1','+stopfdc=0',
                '+stopfdcdata=512','+stoppic=0','+stopppi=0','+maxvram=100000','+timecap=2000000000'])
            results['board']['sector_boundary_reached']='data_reads=512' in log
            results['board']['hardware_wait_oracle']=False
            results['board']['limitation']='Inherited boot bench forces READY high; runnable board also ties D94 A4 high.'
    finally:
        results['cosim_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.cosim,text=True).strip()
        results['verilator']=subprocess.check_output(['verilator','--version'],text=True).strip()
        (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
