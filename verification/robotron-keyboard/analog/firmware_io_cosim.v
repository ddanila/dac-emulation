`timescale 1ns/1ps
// Service fixture: BR1/BR2 open, external 1 MHz clock and reset at CPU-side pins.
// The board oscillator/reset generator is outside this focused I/O experiment.
module firmware_io_cosim #(parameter ELECTRICAL_LOGIC_PULLUPS=0, ELECTRICAL_CPU_PULLUPS=0)(input fixture_clk, fixture_reset_n,
                         input [7:0] sense, input receiver_data, receiver_clock,
                         input [2:0] logic_control, input cpu_pullup_n, bus_request_n,
                         output [1:0] logic_sink,
                         output data_sink, clock_sink, output [1:0] leds,
                         output [12:0] column_sink);
 wire clk, reset_n;
 controller_service service_boundary(.oscillator(1'b0),.reset_source_n(1'b1),
  .br1_closed(1'b0),.br2_closed(1'b0),.external_clk(fixture_clk),
  .external_reset_n(fixture_reset_n),.cpu_clk(clk),.cpu_reset_n(reset_n));
 boot_cosim #(.ELECTRICAL_MATRIX(1),.ELECTRICAL_OUTPUTS(1),
  .ELECTRICAL_LOGIC_PULLUPS(ELECTRICAL_LOGIC_PULLUPS),
  .ELECTRICAL_CPU_PULLUPS(ELECTRICAL_CPU_PULLUPS)) board(
  .clk(clk),.reset_n(reset_n),.sense(sense),.receiver_data(receiver_data),
  .receiver_clock(receiver_clock),.data_sink(data_sink),.clock_sink(clock_sink),
  .cpu_pullup_n(cpu_pullup_n),.bus_request_n(bus_request_n),
  .logic_control(logic_control),.logic_sink(logic_sink),
  .leds(leds),.column_sink(column_sink));
endmodule
