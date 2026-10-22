`timescale 1ns/1ps
module pin_timing;
 parameter EARLY=0;
 reg clk=0,reset_n=0,wait_n=1;
 wire [15:0] address;wire [7:0] dout;
 wire mreq_n,iorq_n,rd_n,wr_n;
 reg [7:0] mem[0:65535];reg [1023:0] file;
 wire [7:0] di=!mreq_n?mem[address]:8'ha6;
 tv80n #(.T2Write(EARLY)) cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),
 .int_n(1'b1),.nmi_n(1'b1),.busrq_n(1'b1),.di(di),.A(address),.dout(dout),
 .mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n));
 integer cycle,i,reset_at,wait_at,wait_end;
 initial begin
  for(i=0;i<65536;i=i+1)mem[i]=0;
  if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");
  $readmemh(file,mem);
  if(!$value$plusargs("reset_at=%d",reset_at))$fatal(1,"reset missing");
  if(!$value$plusargs("wait_at=%d",wait_at))$fatal(1,"wait missing");
  if(!$value$plusargs("wait_end=%d",wait_end))$fatal(1,"wait end missing");
  // Inputs change a quarter cycle away from either sampling edge.
  repeat(4)begin #5;clk=1;#5;clk=0;end
  for(cycle=0;cycle<400;cycle=cycle+1)begin
   #2;reset_n=!(cycle>=reset_at&&cycle<reset_at+16);wait_n=!(cycle>=wait_at&&cycle<wait_end);
   #3;clk=1;#1;report(0);
   #5;clk=0;#1;report(1);
   #0;
  end
  $finish;
 end
 task report(input integer e);begin
  $display("PIN %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",cycle,e,reset_n,wait_n,address,wr_n?di:dout,!mreq_n,!iorq_n,!rd_n,!wr_n);
  $display("DRIVE %0d %0d %0d %0d",cycle,e,address,dout);
  $display("CORE %0d %0d %0d %0d %0d %0d %0d",cycle,e,cpu.tstate,cpu.iorq,cpu.write,cpu.i_tv80_core.BusB,dout);
 end endtask
 always @(negedge wr_n)if(reset_n&&!mreq_n)mem[address]=dout;
endmodule
