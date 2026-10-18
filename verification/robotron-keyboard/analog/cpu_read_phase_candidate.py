"""Experimental non-M1 falling-edge input latch; not a qualified U880 wrapper."""


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
