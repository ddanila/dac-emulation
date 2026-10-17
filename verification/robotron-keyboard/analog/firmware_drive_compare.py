#!/usr/bin/env python3
"""Compare S600 logical behavior with WR-only and write-cycle data-drive boundaries."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from controller_interface import generate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROM_SHA256 = '4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resolved-bus',action='store_true',help='Also route ROM data through the shared bus')
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-analog/firmware-drive')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'scope':__doc__,
            'resolvedBus':args.resolved_bus,
            'boundary':'Original firmware scenarios and digital matrix; not analog or physical CPU timing qualification'}
    try:
        if sha(args.rom)!=ROM_SHA256:raise ValueError('Expected standard S600 image')
        report['romSha256']=sha(args.rom)
        (out/'s600.hex').write_text('\n'.join(f'{b:02x}' for b in args.rom.read_bytes())+'\n')
        source=HERE.parent/'firmware_tb.v';original=source.read_text()
        report['originalTestbenchSha256']=sha(source)
        old=' controller board(address,dout,iorq_n,wr_n,contacts,read_data,leds,ta_daten,ta_takt);'
        if original.count(old)!=1:raise ValueError('Unexpected firmware testbench boundary')
        replacement=''' wire [7:0] sense;wire [12:0] column_sink;
 wire cpu_drive=cpu_reset_n && busak_n && cpu.write;
 controller_analog board(.address(address),.cpu_data(dout),.iorq_n(iorq_n),.wr_n(wr_n),
 .cpu_drive(cpu_drive),.sense(sense),.column_sink(column_sink),.read_data(read_data),
 .leds(leds),.ta_daten(ta_daten),.ta_takt(ta_takt));
'''
        for row in range(8):
            replacement+=f' assign sense[{row}]='+' | '.join(f'(contacts[{col*8+row}] && column_sink[{col}])' for col in range(13))+';\n'
        if args.resolved_bus:
            replacement = replacement.replace(' wire [7:0] sense;', ' wire [10:0] rom_address;wire [7:0] sense;')
            replacement = replacement.replace('.cpu_drive(cpu_drive),',
                '.cpu_drive(cpu_drive),.mreq_n(mreq_n),.rom_data(rom[rom_address]),.rom_address(rom_address),')
        updated = original.replace(old,replacement)
        if args.resolved_bus:
            old_di='assign di=!mreq_n?rom[address[10:0]]:read_data;'
            if updated.count(old_di)!=1:raise ValueError('Unexpected direct-ROM CPU boundary')
            updated=updated.replace(old_di,'assign di=read_data;')
        (out/'new_tb.v').write_text(updated)
        (out/'controller_analog.v').write_text(generate(explicit_cpu_drive=True,resolved_bus=args.resolved_bus))
        tv80=ROOT/'third_party/cpu/tv80';pin=json.loads((tv80/'SOURCE.json').read_text())
        for name,digest in pin['files'].items():
            if sha(tv80/name)!=digest:raise ValueError('Changed TV80 source')
        report['tv80']=pin
        common=[*sorted(tv80.glob('*.v')),HERE.parent/'chips.v',HERE.parent/'generated/controller.v']
        report['sources']={str(path):sha(path) for path in [*common,Path(__file__),out/'new_tb.v',out/'controller_analog.v']}
        traces={}
        for mode,tb in [('old',source),('new',out/'new_tb.v')]:
            subprocess.run(['iverilog','-g2012','-s','firmware_tb','-o',str(out/f'{mode}.vvp'),
                            *map(str,common),str(out/'controller_analog.v'),str(tb)],check=True)
            with (out/f'{mode}.log').open('w') as log:
                subprocess.run(['vvp',f'{mode}.vvp','+rom=s600.hex'],cwd=out,stdout=log,
                               stderr=subprocess.STDOUT,check=True,timeout=600)
            traces[mode]=[line for line in (out/f'{mode}.log').read_text().splitlines() if line.startswith(('BIT ','EDGE ','LED '))]
        if not traces['old'] or not any(line.startswith('BIT ') for line in traces['old']):
            raise ValueError('Firmware workload produced no serial observations')
        for index,(a,b) in enumerate(zip(traces['old'],traces['new'])):
            if a!=b:
                report['firstDifference']={'index':index,'old':a,'new':b}
                raise ValueError('Firmware observations changed with data-drive boundary')
        if len(traces['old'])!=len(traces['new']):raise ValueError('Firmware observation trace lengths differ')
        report['observationSha256']=hashlib.sha256('\n'.join(traces['old']).encode()).hexdigest()
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'report.json')


if __name__=='__main__':main()
