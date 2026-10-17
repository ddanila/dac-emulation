`timescale 1ns/1ps
module matrix_interface_tb;
 parameter COUNT=1;
 reg [23:0] vectors[0:COUNT-1];
 reg [15:0] address;
 reg [7:0] sense;
 wire [12:0] column_sink;
 wire [7:0] read_data;
 wire [1:0] leds;
 wire ta_daten,ta_takt;
 integer i;
 controller_analog board(.address(address),.cpu_data(8'b0),.iorq_n(1'b0),.wr_n(1'b1),
  .sense(sense),.column_sink(column_sink),.read_data(read_data),.leds(leds),
  .ta_daten(ta_daten),.ta_takt(ta_takt));
 initial begin
  $readmemh("matrix-vectors.hex",vectors);
  for(i=0;i<COUNT;i=i+1) begin
   {address,sense}=vectors[i];
   #10;
   if(column_sink !== address[12:0])
    $fatal(1,"column driver mismatch vector %0d: %h != %h",i,column_sink,address[12:0]);
   if(read_data !== sense)
    $fatal(1,"sense/latch/bus mismatch vector %0d: %h != %h",i,read_data,sense);
  end
  $display("MATRIX_INTERFACE_PASS %0d",COUNT);
  $finish;
 end
endmodule
