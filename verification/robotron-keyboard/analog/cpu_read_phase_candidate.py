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
