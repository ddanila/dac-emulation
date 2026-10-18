"""Experimental non-M1 falling-edge input latch; not a qualified U880 wrapper."""

import hashlib
from pathlib import Path

CIRCUIT_PROFILES = ('tv80', 'falling-indexed-candidate')


def circuit_sources(vendor, output, profile):
    """Select explicit circuit CPU sources after the caller verifies the vendor."""
    if profile not in CIRCUIT_PROFILES:
        raise ValueError('Unsupported circuit CPU profile: ' + profile)
    sources = sorted(vendor.glob('*.v'))
    report = {'profile': profile, 'qualified': False,
              'sampling': 'M1 rising; non-M1 rising' if profile == 'tv80' else
                          'M1 rising; non-M1 following falling edge',
              'boundary': 'Behavioral CPU experiment; not calibrated U880 pin timing or synthesis qualification'}
    if profile != 'tv80':
        generated = []
        for name, transform in (('tv80n.v', generate), ('tv80_core.v', generate_core)):
            path = output / ('candidate_' + name)
            path.write_text(transform((vendor / name).read_text()))
            generated.append(path)
        sources = [path for path in sources if path.name not in ('tv80n.v', 'tv80_core.v')] + generated
        report['generatedSha256'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in generated}
        report['generatorSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return sources, report


def generate(source):
    old = "  always @(posedge clk)\n"
    if source.count(old) != 1:
        raise ValueError('Unexpected TV80 input-register process')
    source = source.replace(old, """  reg delayed_read=0;
  always @(posedge clk)
    if (!reset_n) delayed_read <= 0;
    else delayed_read <= !mcycle[0] && tstate[2] && wait_n;
  always @(posedge clk or negedge clk)
""")
    old = "if (tstate[2] && wait_n == 1'b1)"
    if source.count(old) != 1:
        raise ValueError('Unexpected TV80 input-register enable')
    return source.replace(old, "if ((clk && mcycle[0] && tstate[2] && wait_n == 1'b1) || (!clk && delayed_read))")


def generate_core(source):
    """Move only the indexed non-M1 opcode input to the falling edge."""
    import re
    source, count = re.subn(
        r"if \(ISet == 2'b01 && mcycle\[6\] \)\s+begin\s+IR <= `TV80DELAY dinst;\s+end",
        "// Indexed opcode sampled on following falling edge.", source)
    if count != 1 or source.count("endmodule") != 1:
        raise ValueError("Unexpected TV80 indexed opcode process")
    tail = """  reg indexed_read_pending=0;
  always @(posedge clk or negedge reset_n)
    if (!reset_n) indexed_read_pending <= 0;
    else indexed_read_pending <= ClkEn && tstate[2] && wait_n &&
                                 ISet==2'b01 && mcycle[6];
  always @(negedge clk)
    if (reset_n && indexed_read_pending) IR <= dinst;
"""
    return source.replace("endmodule", tail + "endmodule")
