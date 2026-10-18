"""Separate schematic bus drivers from voltage-derived receiver logic."""
import json
import re
from pathlib import Path

from bus_inventory import DATA_PINS, inventory
from circuit import load
from controller_interface import generate as generate_controller
from cpu_read_phase_candidate import CIRCUIT_PROFILES


def generate(rom_timing=False, latch_timing=False):
    components, _ = load()
    inventory(components, json.loads(Path(__file__).with_name('bus_limits.json').read_text()))
    source = generate_controller(explicit_cpu_drive=True, resolved_bus=True)
    source = source.replace('module controller_analog #(', 'module controller_electrical_bus #(')
    source = source.replace('input [7:0] sense,',
                            'input [7:0] bus_sense, output [23:0] bus_low, bus_high, input [7:0] sense,')
    source = source.replace(');\n', ');\nwire [7:0] cpu_driver, rom_driver, latch_driver;\n', 1)
    declarations = []
    # Keep the original chip instance and its control pins. Only its bus outputs
    # terminate at separate driver wires instead of the receiver nets.
    matches = re.findall(r'^chip_I8282 A4\([^\n]+$', source, re.M)
    if len(matches) != 1:
        raise ValueError('Unexpected generated latch instance')
    latch = matches[0]
    for bit, pin in enumerate(DATA_PINS['A4'][2]):
        old = f'.p{pin}(n_D{bit})'
        if latch.count(old) != 1:
            raise ValueError('Unexpected generated latch bus pin')
        latch = latch.replace(old, f'.p{pin}(latch_driver[{bit}])')
    source = source.replace(matches[0], latch)
    for bit in range(8):
        pullup = f'pullup(n_D{bit});'
        if source.count(pullup) != 1:
            raise ValueError('Unexpected generated bus pullup')
        source = source.replace(pullup, f'assign n_D{bit}=bus_sense[{bit}];')
        pattern = rf'^assign n_D{bit}=([^;]+);$'
        assignments = re.findall(pattern, source, re.M)
        for driver in ('cpu', 'rom'):
            candidates = [a for a in assignments if f'{driver}_data[{bit}]' in a]
            if len(candidates) != 1:
                raise ValueError('Unexpected generated bus driver assignment')
            old = f'assign n_D{bit}={candidates[0]};'
            source = source.replace(old, f'assign {driver}_driver[{bit}]={candidates[0]};')
        for index, driver in enumerate(('cpu', 'rom', 'latch')):
            signal = f'{driver}_driver[{bit}]'
            # Independent low/high enables preserve release (00) and unknown
            # drive (XX). Opposing devices remain separate for analog resolution.
            for state, output in ((0, 'low'), (1, 'high')):
                declarations.append(
                    f"assign bus_{output}[{8 * index + bit}]=({signal}===1'bz) ? 1'b0 : "
                    f"({signal}===1'b{state}) ? 1'b1 : ({signal}===1'b{1-state}) ? 1'b0 : 1'bx;")
    if len(re.findall(r'^assign n_D[0-7]=bus_sense\[[0-7]\];$', source, re.M)) != 8:
        raise ValueError('Incomplete electrical bus receiver boundary')
    source = source.replace('endmodule', '\n'.join(declarations) + '\nendmodule')
    if rom_timing:
        rom = components['A8']
        def net(pin):
            return 'n_' + re.sub('[^a-zA-Z0-9_]', '_', rom['pins'][pin].lstrip('/'))
        for bit in range(8):
            source, count = re.subn(rf'^assign rom_driver\[{bit}\]=[^;]+;$',
                                   f'assign rom_driver[{bit}]=rom_timed[{bit}];', source, flags=re.M)
            if count != 1:
                raise ValueError('Unexpected ROM timing boundary')
        source = source.replace('wire [7:0] cpu_driver, rom_driver, latch_driver;',
                                'wire [7:0] cpu_driver, rom_driver, latch_driver, rom_timed;')
        source = source.replace('endmodule',
            'eprom2716_read_envelope rom_access(.address(rom_address),.data(rom_data),'
            f'.ce_n({net("18")}),.oe_n({net("20")}),.q(rom_timed));\nendmodule')
        source += '\n' + Path(__file__).with_name('eprom2716.v').read_text()
    if latch_timing:
        if source.count('chip_I8282 A4(') != 1:
            raise ValueError('Unexpected latch timing boundary')
        source = source.replace('chip_I8282 A4(', 'chip_I8282_timed A4(')
        source += '\n' + Path(__file__).with_name('i8282_timing.v').read_text()
    return source


def generate_service(electrical_wr=False, cpu_profile='tv80', rom_timing=False, latch_timing=False):
    """Reuse TV80/ROM/service behavior while replacing only the bus boundary."""
    here = Path(__file__).resolve().parent
    if cpu_profile not in CIRCUIT_PROFILES:
        raise ValueError('Unsupported circuit CPU profile: ' + cpu_profile)

    def replace_once(source, old, new):
        if source.count(old) != 1:
            raise ValueError('Unexpected firmware bus boundary: ' + old)
        return source.replace(old, new)

    boot = (here / 'boot_cosim.v').read_text()
    boot = replace_once(boot, 'module boot_cosim #(', 'module boot_electrical_bus #(')
    boot = replace_once(boot, 'output data_sink,',
                        'input [7:0] bus_sense, output [23:0] bus_low, bus_high, output data_sink,')
    boot = replace_once(boot, 'controller_analog #(', 'controller_electrical_bus #(')
    boot = replace_once(boot, '.logic_control(logic_control),.logic_sink(logic_sink),',
                        '.bus_sense(bus_sense),.bus_low(bus_low),.bus_high(bus_high),\n'
                        '   .logic_control(logic_control),.logic_sink(logic_sink),')
    boot = replace_once(boot, 'initial $readmemh',
                        'initial if(!RESOLVED_BUS || !EXPLICIT_CPU_DRIVE || !ELECTRICAL_MATRIX)\n'
                        '  $fatal(1,"Electrical bus requires resolved ROM, CPU drive intent and matrix feedback");\n'
                        ' initial $readmemh')
    # Observe the actual tv80n input-register sampling predicate. This is not a
    # claim that its edge phase equals the U880's published M2-M5 pin timing.
    boot = replace_once(boot, 'endmodule', '''reg [7:0] bus_sample_value;
 always @(posedge clk) begin
  if(reset_n===1'b1 && cpu.tstate[2]===1'b1 && cpu.wait_n===1'b1 &&
     rd_n===1'b0 && (mreq_n===1'b0 || iorq_n===1'b0)) begin
   $display("BUS_SAMPLE %0t %04x %02x %b %b %b",$time,address,di,mreq_n,iorq_n,m1_n);
   bus_sample_value <= di;
   // Postponed-region observation sees the completed nonblocking input latch.
   // It must not depend on a later clock edge outside the capture interval.
   $strobe("BUS_LATCH %0t %02x %02x",$time,bus_sample_value,cpu.di_reg);
  end
 end
endmodule''')
    if cpu_profile != 'tv80':
        boot = replace_once(boot, 'always @(posedge clk) begin\n  if(reset_n',
                            'always @(posedge clk or negedge clk) begin\n  if(reset_n')
        boot = replace_once(boot,
                            "cpu.tstate[2]===1'b1 && cpu.wait_n===1'b1 &&\n     rd_n",
                            "((clk===1'b1 && cpu.mcycle[0]===1'b1 &&\n"
                            "       cpu.tstate[2]===1'b1 && cpu.wait_n===1'b1) ||\n"
                            "      (clk===1'b0 && cpu.delayed_read===1'b1)) &&\n     rd_n")
    service = (here / 'firmware_io_cosim.v').read_text()
    service = replace_once(service, 'module firmware_io_cosim #(', 'module firmware_io_electrical_bus #(')
    service = replace_once(service, 'output [1:0] logic_sink,',
                           'input [7:0] bus_sense, output [23:0] bus_low, bus_high, output [1:0] logic_sink,')
    service = replace_once(service, 'boot_cosim #(', 'boot_electrical_bus #(')
    service = replace_once(service, '.logic_control(logic_control),.logic_sink(logic_sink),',
                           '.bus_sense(bus_sense),.bus_low(bus_low),.bus_high(bus_high),\n'
                           '  .logic_control(logic_control),.logic_sink(logic_sink),')
    if electrical_wr:
        boot = replace_once(boot, 'output [23:0] bus_low, bus_high,',
                            'output [23:0] bus_low, bus_high, output wr_low, wr_high,')
        boot = replace_once(boot, 'endmodule', r"""// U880D printed pp. 9-10: reset makes controls inactive; BUSACK
 // acknowledges high-impedance control outputs. TV80 provides intent only.
 wire [1:0] wr_drive = reset_n===1'b0 ? 2'b01 :
                      reset_n!==1'b1 ? 2'bxx :
                      busak_n===1'b0 ? 2'b00 :
                      busak_n!==1'b1 ? 2'bxx :
                      wr_n===1'b0 ? 2'b10 : wr_n===1'b1 ? 2'b01 : 2'bxx;
 assign {wr_low,wr_high}=wr_drive;
 always @(wr_drive) $display("WR_DRIVE %0t %b",$time,wr_drive);
endmodule""")
        service = replace_once(service, 'output [23:0] bus_low, bus_high,',
                               'output [23:0] bus_low, bus_high, output wr_low, wr_high,')
        service = replace_once(service, '.bus_sense(bus_sense),',
                               '.wr_low(wr_low),.wr_high(wr_high),.bus_sense(bus_sense),')
    return generate(rom_timing=rom_timing, latch_timing=latch_timing) + '\n' + boot + '\n' + service
