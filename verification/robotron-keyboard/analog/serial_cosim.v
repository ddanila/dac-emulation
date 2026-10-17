`timescale 1ns/1ps
// Raw bit transport fixture with explicit setup/hold, not S600 protocol framing.
module serial_cosim(input rx_data, input rx_clock, output data_sink, output clock_sink);
 reg d0=1,wr_n=1,armed=0;
 reg [31:0] pattern=32'ha55a00ff;
 integer sent,received=0;
 serial_driver_reference driver(d0,wr_n,data_sink,clock_sink);
 initial begin
  #10000; armed=1;
  for(sent=0;sent<32;sent=sent+1) begin
   d0=pattern[sent];
   #4000; wr_n=0;
   #2000; wr_n=1;
   #4000;
  end
  #5000;
  if(received!=32) $fatal(1,"received %0d bits, expected 32",received);
  $display("SERIAL_TRANSPORT_PASS %08x",pattern);
  $fflush();
 end
 always @(posedge rx_clock) if(armed && rx_clock===1'b1) begin
  if(received>=32) $fatal(1,"extra receiver clock edge");
  if(rx_data !== ~pattern[received])
   $fatal(1,"serial bit %0d: receiver=%b expected=%b",received,rx_data,~pattern[received]);
  $display("RECEIVED %0t %0d %b",$time,received,~rx_data);
  received=received+1;
 end
endmodule
