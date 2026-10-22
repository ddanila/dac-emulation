`timescale 1ns/1ps
module probe;
 reg clk=0,reset_n=0,wait_n=1;
 always #5 clk=~clk;
 wire [15:0] a;wire [7:0] dout;wire mreq_n,iorq_n,rd_n,wr_n,halt_n;
 reg [7:0] memory[0:65535];reg [1023:0] file;integer i;
 wire [7:0] di=!iorq_n?8'h34:memory[a];
 tv80_io_candidate cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),.int_n(1'b1),.nmi_n(1'b1),.busrq_n(1'b1),.di(di),.A(a),.dout(dout),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.halt_n(halt_n));
 integer start,stop;time origin;reg seen=0,released=0;
 initial begin
  if(!$value$plusargs("start=%d",start)||!$value$plusargs("stop=%d",stop))$fatal(1,"parameters missing");
  for(i=0;i<65536;i=i+1)memory[i]=0;
  if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");
  $readmemh(file,memory);
  #42;reset_n=1;
  #4000;
  $display("HALT %0d",!halt_n);
  $display("A %0d",cpu.base.i_tv80_core.ACC);
  $finish;
 end
 always @(negedge rd_n)if(!iorq_n&&!seen)begin
  seen=1;origin=$time;
  // Transitions occur 1 ns BEFORE each specified half-edge, outside races.
  #(start*5-1);wait_n=0;
  #((stop-start)*5);wait_n=1;
 end
 always @(negedge wr_n)if(reset_n&&!mreq_n)memory[a]=dout;
 // IORQ and RD release together, so observe the selected read as one expression.
 wire read_active=!iorq_n&&!rd_n;
 always @(negedge read_active)if(seen&&reset_n&&!released)begin released=1;$display("RELEASE %0d",($time-origin)/5);end
endmodule
