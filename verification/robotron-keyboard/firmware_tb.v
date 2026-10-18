`timescale 1ns/1ps
module firmware_tb #(
 parameter ROM_READ_ENVELOPE=0,
 parameter CLOCK_HALF_NS=5,
 parameter FLOATING_IO_OVERRIDE=0,
 parameter [7:0] FLOATING_IO_VALUE=8'hff
);
 reg clk=0,reset_n=0;always #(CLOCK_HALF_NS) clk=~clk;
 wire cpu_clk,cpu_reset_n;
 // Reproducible bench stimulus enters the CPU sides of open BR1/BR2.
 controller_service service_boundary(.oscillator(1'b0),.reset_source_n(1'b1),
  .br1_closed(1'b0),.br2_closed(1'b0),.external_clk(clk),
  .external_reset_n(reset_n),.cpu_clk(cpu_clk),.cpu_reset_n(cpu_reset_n));
 wire [15:0] address;wire [7:0] dout,di,read_data;wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 reg [103:0] contacts=0;wire [1:0] leds;wire ta_daten,ta_takt;
 reg [7:0] rom[0:2047];reg [1023:0] file,wave;integer cycle=-16,wave_start=0,wave_end=4600000;reg wave_enabled=0;
 tv80n cpu(.reset_n(cpu_reset_n),.clk(cpu_clk),.wait_n(1'b1),.int_n(1'b1),.nmi_n(1'b1),.busrq_n(1'b1),.di(di),.A(address),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 controller board(address,dout,iorq_n,wr_n,contacts,read_data,leds,ta_daten,ta_takt);
 // A15 low disables the 8282 outputs. The standard digital board's pullups
 // are a boundary convention, not evidence that the physical bus reads FF.
 // This fixture override explores firmware dependence on released I/O reads.
 wire [7:0] rom_read;
 generate if(ROM_READ_ENVELOPE) begin: timed_rom
  eprom2716_read_envelope access(.address(address[10:0]),.data(rom[address[10:0]]),
   .ce_n(1'b0),.oe_n(mreq_n),.q(rom_read));
 end else begin: immediate_rom
  assign rom_read=rom[address[10:0]];
 end endgenerate
 // Direct CPU input remains a digital fixture; this does not resolve bus
 // contention or output release in SPICE. Clock units must match the ns model.
 assign di=!mreq_n?rom_read:
           FLOATING_IO_OVERRIDE && !iorq_n && !rd_n && !address[15] ?
           FLOATING_IO_VALUE:read_data;
 initial begin
  if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");$readmemh(file,rom);
  if($value$plusargs("wave=%s",wave))begin
   wave_enabled=1;
   if($value$plusargs("wave_start=%d",wave_start))begin end
   if($value$plusargs("wave_end=%d",wave_end))begin end
   $dumpfile(wave);$dumpvars(0,firmware_tb);
   if(wave_start>0)$dumpoff;
  end
 end
 always @(negedge clk)begin
  cycle=cycle+1;
  if(cycle==0)reset_n=1;
  case(cycle)
   200000:contacts[61]=1;
   400000:contacts[61]=0;
   600000:contacts[65]=1;
   800000:contacts[61]=1;
   1000000:contacts=0;
   1200000:contacts[71]=1;
   1400000:contacts=0;
   1450000:contacts[69]=1;
   1550000:contacts=0;
   1600000:contacts[64]=1;
   1800000:contacts[61]=1;
   2000000:contacts=0;
   2200000:contacts[61]=1;
   2400000:contacts[70]=1;
   3800000:contacts[70]=0;
   4200000:begin reset_n=0;contacts=0;end
   4200016:reset_n=1;
   4400000:contacts[61]=1;
  endcase
  if(cycle>=0&&cycle%200000==199999)$display("LED %0d %0d",cycle,leds);
  if(wave_enabled && cycle==wave_start)$dumpon;
  if(wave_enabled && cycle>=wave_end)begin $dumpflush;$finish;end
  if(cycle==4600000)$finish;
 end
 always @(leds) if(reset_n && cycle>=0)$display("EDGE %0d %0d",cycle,leds);
 always @(posedge ta_takt) if(reset_n)begin #1;$display("BIT %0d %0d",cycle,~ta_daten);end
endmodule
