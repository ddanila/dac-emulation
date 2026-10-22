`timescale 1ns/1ps
module probe;
 reg clk=0,reset_n=0,int_n=1,nmi_n=1;
 always #5 clk=~clk;
 reg [7:0] memory[0:65535];reg [1023:0] file;integer mode,value,i,accesses=0;
 wire [15:0] a;wire [7:0] dout;wire m1_n,mreq_n,iorq_n,rd_n,wr_n,halt_n;
 wire [7:0] di=!mreq_n?memory[a]:value[7:0];
 tv80_io_candidate cpu(.clk(clk),.reset_n(reset_n),.wait_n(1'b1),.int_n(int_n),.nmi_n(nmi_n),.busrq_n(1'b1),.di(di),.A(a),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.halt_n(halt_n));
 initial begin
  if(!$value$plusargs("rom=%s",file)||!$value$plusargs("mode=%d",mode)||!$value$plusargs("value=%d",value))$fatal(1,"arguments missing");
  $readmemh(file,memory);#42;reset_n=1;
  #6000;$display("RESULT %0d %0d %0d %0d",memory[36864],memory[36865],accesses,!halt_n);$finish;
 end
 always @(negedge iorq_n)if(m1_n&&reset_n)begin
  accesses=accesses+1;
  #1;if(mode)nmi_n=0;else int_n=0;
 end
 always @(negedge wr_n)if(reset_n&&!mreq_n)memory[a]=dout;
endmodule
