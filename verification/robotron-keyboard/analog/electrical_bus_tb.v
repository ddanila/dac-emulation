`timescale 1ns/1ps
module electrical_bus_tb;
 reg [15:0] address=0;
 reg [7:0] cpu_data=0,rom_data=8'ha5,sense=8'h5a,bus_sense=8'h96;
 reg cpu_drive=0,mreq_n=1,iorq_n=1,wr_n=1;
 wire [7:0] read_data;
 wire [23:0] bus_low,bus_high;
 wire ta_daten;
 controller_electrical_bus board(.address(address),.cpu_data(cpu_data),
 .iorq_n(iorq_n),.wr_n(wr_n),.cpu_drive(cpu_drive),.mreq_n(mreq_n),
 .rom_data(rom_data),.sense(sense),.bus_sense(bus_sense),
 .bus_low(bus_low),.bus_high(bus_high),.read_data(read_data),.ta_daten(ta_daten));
 initial begin
  #10;
  if(bus_low!==0 || bus_high!==0 || read_data!==8'h96)
   $fatal(1,"released drivers or receiver isolation");
  mreq_n=0;cpu_drive=1;cpu_data=8'h5a;
  #10;
  if(bus_low[7:0]!==8'ha5 || bus_high[7:0]!==8'h5a ||
     bus_low[15:8]!==8'h5a || bus_high[15:8]!==8'ha5 ||
     bus_low[23:16]!==0 || bus_high[23:16]!==0)
   $fatal(1,"opposing CPU/ROM drivers must remain independent");
  if(read_data!==8'h96) $fatal(1,"digital drivers leaked onto sensed bus");
  cpu_drive=0;mreq_n=1;iorq_n=0;address=16'h8000;
  #10;
  if(bus_low[23:16]!==8'ha5 || bus_high[23:16]!==8'h5a ||
     bus_low[15:0]!==0 || bus_high[15:0]!==0)
   $fatal(1,"latch driver pin order or release");
  iorq_n=1;address=0;cpu_drive=1;cpu_data=8'bxxxxxxxx;bus_sense=8'bxxxxxxxx;
  #10;
  if(bus_low[7:0]!==8'bxxxxxxxx || bus_high[7:0]!==8'bxxxxxxxx ||
     read_data!==8'bxxxxxxxx || ta_daten!==1'bx)
   $fatal(1,"unknown drive or receiver voltage hidden");
  cpu_drive=0;bus_sense=8'bzzzzzzzz;
  #10;
  if(bus_low!==0 || bus_high!==0 || read_data!==8'bzzzzzzzz)
   $fatal(1,"implicit digital bus pullups remain");
  bus_sense=8'h01;
  #10;if(ta_daten!==1'b0)$fatal(1,"7406 data input does not use electrical sense");
  $display("ELECTRICAL_BUS_INTERFACE_PASS");$finish;
 end
endmodule
