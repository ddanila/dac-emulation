`timescale 1ns/1ps
module probe;
 reg clk=0,reset_n=0,wait_n=1,int_n=1,nmi_n=1,busrq_n=1;
 wire [15:0] a;wire [7:0] dout;
 wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 reg [7:0] mem[0:65535];reg [1023:0] file;
 wire [7:0] di=!mreq_n?mem[a]:8'hff;
 `CPU cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),.int_n(int_n),.nmi_n(nmi_n),.busrq_n(busrq_n),.di(di),.A(a),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 integer cycle,i,mode,ack=0,busack=0;
 initial begin
  for(i=0;i<65536;i=i+1)mem[i]=0;
  if(!$value$plusargs("rom=%s",file)||!$value$plusargs("mode=%d",mode))$fatal(1,"parameters missing");
  $readmemh(file,mem);
  repeat(4)begin #5;clk=1;#5;clk=0;end
  for(cycle=0;cycle<600;cycle=cycle+1)begin
   #2;reset_n=1;int_n=!(mode==1&&cycle>=200&&cycle<230);nmi_n=!(mode==2&&cycle==200);
   wait_n=!(mode==3&&cycle>=10&&cycle<15);busrq_n=!(mode==4&&cycle>=10&&cycle<30);
   #3;clk=1;#1;report(0);
   #4;clk=0;#1;report(1);
  end
  $display("RESULT %0d %0d %0d %0d %0d",mem[32768],mem[32769],mem[32770],ack,busack);
  $finish;
 end
 task report(input integer edge_id);begin
  $display("PIN %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",cycle,edge_id,a,dout,m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n);
  if(!m1_n&&!iorq_n)ack=ack+1;
  if(!busak_n)busack=busack+1;
 end endtask
 always @(negedge wr_n)if(reset_n&&!mreq_n)mem[a]=dout;
endmodule
