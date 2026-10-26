`timescale 1ps/1ps
module input_tick_probe(input signal_in, output echo);
  assign echo = signal_in;
  always @(signal_in)
    $display("INPUT_TICK %0t %b", $time, signal_in);
endmodule
