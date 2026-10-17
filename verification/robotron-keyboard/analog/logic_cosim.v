`timescale 1ns/1ps
// Bus fixture driven by an external SPICE clock; no HDL timer advances SPICE.
module logic_cosim(input clk, input [2:0] levels, output [1:0] sinks);
 reg [15:0] address=0;
 reg iorq_n=1;
 reg [7:0] sense=8'ha5;
 wire [7:0] data;
 wire [1:0] leds;
 integer phase=0;
 controller_analog #(.ELECTRICAL_LOGIC_PULLUPS(1)) board(
  .address(address),.cpu_data(8'b0),.cpu_drive(1'b0),.iorq_n(iorq_n),.wr_n(1'b1),
  .mreq_n(1'b1),.rom_data(8'b0),.sense(sense),.logic_control(levels),.logic_sink(sinks),
  .read_data(data),.leds(leds));
 always @(posedge clk) begin
  $display("LOGIC_READ %0t %0d %02x %b",$time,phase,data,leds);
  case(phase)
   0: iorq_n=0;
   1: iorq_n=1;
   2: address=16'h8000;
   3: sense=8'h3c;
   4: begin address=16'hc000; iorq_n=0; end
   5: iorq_n=1;
   6: address=0;
   9: $display("LOGIC_FEEDBACK_PASS");
  endcase
  phase=phase+1;
  $fflush();
 end
endmodule
