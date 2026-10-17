#!/usr/bin/env python3
"""Pass raw bits through the reference 7406, electrical cable and receiver fixture."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from failure_evidence import solver_diagnostic

from circuit import load
from output_circuit import output_circuit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PATTERN = 0xA55A00FF


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def driver_wrapper(components):
    c = components['A1']
    if c['type'] != '7406' or set(c['pins']) != {str(i) for i in range(1,15)}:
        raise ValueError('Unexpected serial driver package')
    roles = {components['A5']['pins']['14']: 'd0', components['A5']['pins']['22']: 'wr_n',
             components['L1.4']['pins']['1']: 'data_oc', components['L1.1']['pins']['1']: 'clock_oc',
             '/+5V': "1'b1", '/GND': "1'b0"}
    ports = []
    seen = set()
    for pin, net in c['pins'].items():
        signal = roles.get(net)
        if signal:
            seen.add(signal)
        elif pin in ('1','3','5','9','11','13'):
            signal = "1'b0"  # Other gates are inactive in this fixture.
        else:
            signal = ''
        ports.append(f'.p{pin}({signal})')
    if not {'d0','wr_n','data_oc','clock_oc'} <= seen:
        raise ValueError('Serial driver no longer connects CPU data/write to cable filter')
    return '''module serial_driver_reference(input d0,wr_n,output data_sink,clock_sink);
wire data_oc,clock_oc;
chip_7406 driver(''' + ','.join(ports) + ''');
assign data_sink=data_oc===1'b0 ? 1'b1 : data_oc===1'bz ? 1'b0 : 1'bx;
assign clock_sink=clock_oc===1'b0 ? 1'b1 : clock_oc===1'bz ? 1'b0 : 1'bx;
endmodule
'''


def run(args, components, libs, step, cable_pf):
    out = args.out.resolve() / f'{step}ns-{cable_pf}pf'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trace.txt').unlink(missing_ok=True)
    (out / 'driver.v').write_text(driver_wrapper(components))
    subprocess.run([args.iverilog,'-g2012','-s','serial_cosim','-o',str(out/'serial.vvp'),
                    str(out/'driver.v'),str(HERE/'serial_cosim.v'),str(HERE.parent/'chips.v')],check=True)
    lines, info = output_circuit(components, cable_pf)
    ground = info['hostGround']
    data, clock = [info['serial'][label]['cable'] for label in ('data','clock')]
    lines = ['Robotron raw serial transport through HDL and nominal electrical loads',
             f'Vhost {info["hostSupply"]} {ground} 5', *lines,
             'Vsiso siso_intent 0 0','Vcaps caps_intent 0 0',
             f'Edata receiver_data 0 {data} {ground} 1',
             f'Eclock receiver_clock 0 {clock} {ground} 1',
             'Adata [receiver_data] [rx_data] data_receiver',
             '.model data_receiver adc_bridge(in_low=.8 in_high=2)',
             'Aclock [receiver_clock] [rx_clock] clock_receiver',
             '.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)',
             'Ahdl [rx_data rx_clock] [dsink csink] hdl',
             f'.model hdl d_cosim simulation="{libs["shim"]}" sim_args=["serial.vvp"] delay=1n',
             f'+ lib_args=["{libs["libvvp"]}" "{libs["vpi"]}"]',
             'Adrive [dsink csink] [data_intent clock_intent] drive',
             '.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)',
             '.save v(receiver_data) v(receiver_clock)',
             '.control','set wr_singlescale','set wr_vecnames',f'tran {step}n 340u',
             'wrdata trace.txt v(receiver_data) v(receiver_clock)','quit','.endc','.end']
    (out/'serial.cir').write_text('\n'.join(lines)+'\n')
    with (out/'ngspice.log').open('w') as log:
        subprocess.run([args.ngspice,'-n', '-b','serial.cir'],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    log = (out/'ngspice.log').read_text()
    if solver_diagnostic(log):
        raise ValueError('Solver/HDL diagnostics: '+str(out/'ngspice.log'))
    received = re.findall(r'^RECEIVED (\d+) (\d+) ([01])$',log,re.M)
    if len(received)!=32 or 'SERIAL_TRANSPORT_PASS a55a00ff' not in log:
        raise ValueError('Receiver did not complete bit sequence')
    delays=[]
    for i,(stamp,index,bit) in enumerate(received):
        if int(index)!=i or int(bit)!=((PATTERN>>i)&1):
            raise ValueError('Incorrect received bit ordering/value')
        delay=int(stamp)*1e-12-(14+i*10)*1e-6
        if not 0 < delay < 2e-6:
            raise ValueError('Clock edge outside fixture high interval')
        delays.append(delay)
    rows=[[float(v) for v in line.split()] for line in (out/'trace.txt').read_text().splitlines()[1:]]
    if not rows or any(len(row)!=3 or not all(map(math.isfinite,row)) for row in rows):
        raise ValueError('Invalid receiver waveform')
    if rows[0][0]>1e-9 or rows[-1][0]<340e-6:
        raise ValueError('Incomplete receiver waveform')
    initial=min(rows,key=lambda row:abs(row[0]-5e-6))
    if max(initial[1:])>=.8:
        raise ValueError('Driver did not establish low idle before arming receiver')
    # Independently check data voltage around each observed receiver clock event.
    for stamp,index,bit in received:
        t=int(stamp)*1e-12
        window=[r[1] for r in rows if t-100e-9<=r[0]<=t+100e-9]
        if not window or not (max(window)<.8 if bit=='1' else min(window)>2):
            raise ValueError('Data was not stable around the receiver clock edge')
    return {'stepNs':step,'cablePf':cable_pf,'received':received,
            'clockTransportSeconds':delays,'deckSha256':sha(out/'serial.cir'),
            'generatedDriverSha256':sha(out/'driver.v')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bridge',type=Path,default=ROOT/'build/keyboard-controller-analog/bridge/bridge.json')
    p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-analog/serial-feedback')
    p.add_argument('--ngspice',default='ngspice')
    p.add_argument('--iverilog',default='iverilog')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    path=a.out/'report.json';path.unlink(missing_ok=True)
    report={'passed':False,'scope':__doc__,'runs':[],
            'assumptions':{'bitPatternHex':'a55a00ff','bitOrder':'least significant bit first',
                           'dataSetupSeconds':4e-6,'clockHighSeconds':2e-6,'bitPeriodSeconds':10e-6,
                           'dataThresholdVolts':[.8,2],'clockThresholdVolts':1.4,
                           'loads':'output_circuit.py nominal parameters; no specimen calibration',
                           'scope':'Raw transport fixture, not S600 framing or CPU bus timing'},
            'sources':{name:sha(HERE/name) for name in ('failure_evidence.py', 'serial_cosim.py','serial_cosim.v','output_circuit.py','circuit.py')},
            'chipsSha256':sha(HERE.parent/'chips.v')}
    try:
        components,report['connectivitySha256']=load()
        bridge=json.loads(a.bridge.read_text())
        for lib in bridge['libraries'].values():
            if sha(Path(lib['path']))!=lib['sha256']:raise ValueError('Bridge provenance mismatch')
        report['bridge']=bridge
        libs={k:v['path'] for k,v in bridge['libraries'].items()}
        if any('"' in s or '\n' in s for s in libs.values()):raise ValueError('Unsupported library path')
        report['ngspice']=subprocess.check_output([a.ngspice,'--version'],text=True).strip()
        report['iverilog']=subprocess.run([a.iverilog,'-V'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
        for cable_pf in (1000,2000):
            pair=[]
            for step in (10,5):
                result=run(a,components,libs,step,cable_pf);pair.append(result);report['runs'].append(result)
            for x,y in zip(pair[0]['clockTransportSeconds'],pair[1]['clockTransportSeconds']):
                if abs(x-y)>15e-9:raise ValueError('Clock transport fails timestep refinement within 15 ns')
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:path.write_text(json.dumps(report,indent=2)+'\n')
    print(path)


if __name__=='__main__':main()
