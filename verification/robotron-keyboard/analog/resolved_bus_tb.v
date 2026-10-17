`timescale 1ns/1ps
module resolved_bus_tb;
 reg [15:0] address=0;
 reg [7:0] cpu_data=0,rom_data=8'ha5,sense=8'h5a;
 reg cpu_drive=0,mreq_n=1,iorq_n=1,wr_n=1;
 wire [7:0] read_data;
 wire [10:0] rom_address;
 wire [12:0] column_sink;
 wire [1:0] leds;
 wire ta_daten,ta_takt;
 controller_analog board(.address(address),.cpu_data(cpu_data),.iorq_n(iorq_n),.wr_n(wr_n),
 .cpu_drive(cpu_drive),.mreq_n(mreq_n),.rom_data(rom_data),.rom_address(rom_address),
 .sense(sense),.column_sink(column_sink),.read_data(read_data),.leds(leds),
 .ta_daten(ta_daten),.ta_takt(ta_takt));
 initial begin
  #10;if(read_data!==8'hff)$fatal(1,"released bus lacks pullup resolution");
  address=16'h0123;mreq_n=0;
  #10;if(read_data!==8'ha5 || rom_address!==11'h123)$fatal(1,"ROM read pin mapping");
  address=16'h7123;
  #10;if(read_data!==8'ha5 || rom_address!==11'h123)$fatal(1,"ROM address mirroring");
  address=16'h8000;mreq_n=1;iorq_n=0;
  #10;if(read_data!==8'h5a)$fatal(1,"latch read path");
  address=0;cpu_drive=1;cpu_data=8'h3c;wr_n=0;
  #10;if(read_data!==8'h3c)$fatal(1,"CPU write with ROM/latch released");
  mreq_n=0;cpu_data=8'h5a;
  #10;if(read_data!==8'bx || ta_daten!==1'bx)$fatal(1,"CPU/ROM contention hidden");
  cpu_data=8'ha5;
  #10;if(read_data!==8'ha5)$fatal(1,"matching drivers do not resolve");
  cpu_drive=0;address=16'h8000;wr_n=1;
  #10;if(read_data!==8'bx)$fatal(1,"ROM/latch contention hidden");
  mreq_n=1;address=0;iorq_n=1;
  #10;if(read_data!==8'hff)$fatal(1,"bus release after contention");
  $display("RESOLVED_BUS_PASS");$finish;
 end
endmodule
