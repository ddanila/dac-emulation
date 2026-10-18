`timescale 1ns/1ps
module bus_cosim(input clk, input [7:0] bus_sense, output [23:0] bus_low, bus_high);
 reg [15:0] address=0;
 reg [7:0] cpu_data=0;
 reg cpu_drive=0,mreq_n=1,iorq_n=1;
 wire [7:0] data;
 integer phase=0;
 controller_electrical_bus board(.address(address),.cpu_data(cpu_data),
 .iorq_n(iorq_n),.wr_n(1'b1),.cpu_drive(cpu_drive),.mreq_n(mreq_n),
 .rom_data(8'ha5),.sense(8'h5a),.bus_sense(bus_sense),
 .bus_low(bus_low),.bus_high(bus_high),.read_data(data));
 always @(posedge clk) begin
  $display("BUS_READ %0t %0d %02x",$time,phase,data);
  case(phase)
   0: begin cpu_drive=1; cpu_data=8'hff; end
   1: cpu_data=0;
   2: begin cpu_drive=0; mreq_n=0; end
   3: begin mreq_n=1; iorq_n=0; address=16'h8000; end
   4: begin iorq_n=1; address=0; mreq_n=0; cpu_drive=1; cpu_data=8'h5a; end
   5: cpu_data=8'ha5;
   6: begin mreq_n=1; cpu_drive=0; end
   7: $display("BUS_FEEDBACK_PASS");
  endcase
  phase=phase+1;
  $fflush();
 end
endmodule
