#!/usr/bin/env python3
"""Build an isolated full-bus HDL reference; never rewrite retained candidates."""
from pathlib import Path
from io_repeat_candidate import hdl_core
from io_complete_candidate import hdl_wrapper
from io_flags_candidate import replace_once
from qualify import ROOT
HERE = Path(__file__).resolve().parent


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    vendor = ROOT / 'third_party/cpu/tv80'
    core=hdl_core((vendor / 'tv80_core.v').read_text())
    anchor="      Auto_Wait = 1'b0;\n      if (IntCycle == 1'b1 || NMICycle == 1'b1 )"
    core=replace_once(core,anchor,"      Auto_Wait = 1'b0;\n      if (IntCycle == 1'b1 )")
    for signal in ('NMICycle','IntCycle'):
        anchor="                                  "+signal+" <= `TV80DELAY 1'b1;"
        core=replace_once(core,anchor,anchor+"\n                                  Halt_FF <= `TV80DELAY 1'b0;")
    (out / 'tv80_core.v').write_text(core)
    mcode=(vendor/'tv80_mcode.v').read_text()
    start=mcode.index('                      // NMI')
    end=mcode.index("                  else if (IntCycle == 1'b1 )",start)
    block=mcode[start:end]
    if block.count("TStates = 3'b100;")!=2:raise ValueError('NMI cycle contract changed')
    mcode=mcode[:start]+block.replace("TStates = 3'b100;","TStates = 3'b011;")+mcode[end:]
    start=mcode.index('                      // INT (IM 2)')
    end=mcode.index("                end // case: 8'b00000000",start)
    block=mcode[start:end]
    if block.count("TStates = 3'b100;")!=2:raise ValueError('IM2 cycle contract changed')
    mcode=mcode[:start]+block.replace("TStates = 3'b100;","TStates = 3'b011;")+mcode[end:]
    (out/'tv80_mcode.v').write_text(mcode)
    wrapper = hdl_wrapper((HERE / 'tv80_io_candidate.v').read_text())
    wrapper = replace_once(wrapper, 'wire accepted_wait=read_wait?wait_sampled:wait_n;',
                           'wire accepted_wait=wait_sampled;')
    (out / 'tv80_io_candidate.v').write_text(wrapper)
    base = (vendor / 'tv80n.v').read_text()
    # Opcode fetch uses dinst directly at T3 rising. Other reads sample T3 falling.
    base = replace_once(base, '  always @(posedge clk)\n', '''  reg delayed_read=0;
  always @(posedge clk)
    if (!reset_n) delayed_read <= 0;
    else delayed_read <= !mcycle[0] && !write && !no_read && tstate[2] && wait_n;
  always @(posedge clk or negedge clk)
''')
    base = replace_once(base, "if (tstate[2] && wait_n == 1'b1)",
                        'if ((clk && mcycle[0] && tstate[2] && wait_n) || (!clk && delayed_read))')
    (out / 'tv80n.v').write_text(base)
    (out / 'cpu_bus_candidate.v').write_text((HERE / 'cpu_bus_candidate.v').read_text())
    return [p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v', 'tv80n.v', 'tv80_mcode.v')] + [
        out / 'tv80_core.v', out / 'tv80_mcode.v', out / 'tv80n.v', out / 'tv80_io_candidate.v', out / 'cpu_bus_candidate.v']
