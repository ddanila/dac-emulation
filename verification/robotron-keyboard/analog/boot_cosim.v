`timescale 1ns/1ps
// Clock/reset are analog receiver outputs; matrix sense remains the digital model.
module boot_cosim(input clk, input reset_n,
                  output data_sink, output clock_sink, output [1:0] leds);
 wire [15:0] address;
 wire [7:0] dout, di, read_data;
 wire m1_n, mreq_n, iorq_n, rd_n, wr_n, rfsh_n, halt_n, busak_n;
 wire ta_daten, ta_takt;
 reg [7:0] rom[0:2047];
 integer cycles=0, fetches=0, reads=0, writes=0, clock_edges=0;
 initial $readmemh("s600.hex", rom);
 tv80n cpu(.reset_n(reset_n), .clk(clk), .wait_n(1'b1), .int_n(1'b1),
  .nmi_n(1'b1), .busrq_n(1'b1), .di(di), .A(address), .dout(dout),
  .m1_n(m1_n), .mreq_n(mreq_n), .iorq_n(iorq_n), .rd_n(rd_n),
  .wr_n(wr_n), .rfsh_n(rfsh_n), .halt_n(halt_n), .busak_n(busak_n));
 controller board(address,dout,iorq_n,wr_n,104'b0,read_data,leds,ta_daten,ta_takt);
 assign di=!mreq_n ? rom[address[10:0]] : read_data;
 assign data_sink=(ta_daten===1'bz || ta_daten===1'b1) ? 1'b0 : ta_daten===1'b0 ? 1'b1 : 1'bx;
 assign clock_sink=(ta_takt===1'bz || ta_takt===1'b1) ? 1'b0 : ta_takt===1'b0 ? 1'b1 : 1'bx;
 always @(reset_n) begin
  $display("RESET %0t %b", $time, reset_n);
  if(reset_n===1'b0) begin cycles=0;fetches=0;reads=0;writes=0;end
  $fflush();
 end
 always @(posedge clk) begin
  clock_edges=clock_edges+1;
  if(clock_edges%100000==0) begin $display("CLOCK_PROGRESS %0t %0d",$time,clock_edges);$fflush();end
 end
 always @(posedge clk) if(reset_n===1'b1) begin
  cycles=cycles+1;
  if(!mreq_n && !m1_n && !rd_n) begin
   if(fetches==0) $display("FIRST_FETCH %0t %04x %02x",$time,address,di);
   fetches=fetches+1;
  end
  if(!iorq_n && !rd_n) reads=reads+1;
  if(!iorq_n && !wr_n) writes=writes+1;
  if(cycles%1000==0) $display("BOOT %0t %0d %0d %0d %0d %04x %b",$time,cycles,fetches,reads,writes,address,leds);
 end
endmodule
