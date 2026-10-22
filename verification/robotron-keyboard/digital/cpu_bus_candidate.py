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
    (out / 'tv80_core.v').write_text(hdl_core((vendor / 'tv80_core.v').read_text()))
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
    return [p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v', 'tv80n.v')] + [
        out / 'tv80_core.v', out / 'tv80n.v', out / 'tv80_io_candidate.v', out / 'cpu_bus_candidate.v']
