`timescale 1ns/1ps
// Bus stimulus fixture. Sense voltages return live from SPICE via the input port.
module matrix_cosim(input [7:0] sense, output [12:0] column_sink);
 parameter COUNT=15;
 reg [23:0] vectors[0:COUNT-1];
 reg [15:0] address=16'h8000;
 reg iorq_n=1;
 wire [7:0] read_data;
 wire [1:0] leds;
 wire ta_daten, ta_takt;
 integer i;
 controller_analog board(.address(address),.cpu_data(8'b0),.iorq_n(iorq_n),.wr_n(1'b1),
  .sense(sense),.column_sink(column_sink),.read_data(read_data),.leds(leds),
  .ta_daten(ta_daten),.ta_takt(ta_takt));
 initial begin
  $readmemh("matrix-vectors.hex",vectors);
  #10000;
  for(i=0;i<COUNT;i=i+1) begin
   address=vectors[i][23:8];
   #2000; iorq_n=0;
   #2000;
   if(read_data !== vectors[i][7:0])
    $fatal(1,"live matrix vector %0d: read %h expected %h sense %h",i,read_data,vectors[i][7:0],sense);
   $display("MATRIX_READ %0t %0d %04x %02x",$time,i,address,read_data);
   #1000; iorq_n=1;
   #5000;
  end
  $display("MATRIX_FEEDBACK_PASS %0d",COUNT);
  $fflush();
 end
endmodule
