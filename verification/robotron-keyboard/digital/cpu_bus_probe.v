`timescale 1ns/1ps
module probe;
 reg clk=0,reset_n=0,wait_n=1,int_n=1,nmi_n=1,busrq_n=1;
 wire [15:0] a;wire [7:0] dout;
 wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 wire address_oe,data_oe,control_oe;
 reg [7:0] mem[0:65535];reg [1023:0] file;
 integer late_mode=0,outputs=0,last_output=0;
 reg late_data=0;
 wire [7:0] di=(!mreq_n&&!rd_n)?((late_mode==1 && a==16'h8000)?(late_data?8'h34:8'h12):mem[a]):8'hff;
 cpu_bus_candidate cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),
 .int_n(int_n),.nmi_n(nmi_n),.busrq_n(busrq_n),.di(di),.A(a),.dout(dout),
 .m1_n(m1_n),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),
 .rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n),
 .address_oe(address_oe),.data_oe(data_oe),.control_oe(control_oe));
 integer cycle,i,request_at,release_at,wait_at,wait_end,irq_at,nmi_at;
 initial begin
  for(i=0;i<65536;i=i+1)mem[i]=0;
  if(!$value$plusargs("rom=%s",file))$fatal(1,"ROM missing");
  $readmemh(file,mem);
  if(!$value$plusargs("late=%d",late_mode))late_mode=0;
  if(!$value$plusargs("request=%d",request_at))request_at=999;
  if(!$value$plusargs("release=%d",release_at))release_at=999;
  if(!$value$plusargs("wait=%d",wait_at))wait_at=999;
  if(!$value$plusargs("wait_end=%d",wait_end))wait_end=999;
  if(!$value$plusargs("irq=%d",irq_at))irq_at=999;
  if(!$value$plusargs("nmi=%d",nmi_at))nmi_at=999;
  repeat(4)begin #5;clk=1;#5;clk=0;end
  for(cycle=0;cycle<400;cycle=cycle+1)begin
   #2;reset_n=1;busrq_n=!(cycle>=request_at&&cycle<release_at);
   wait_n=!(cycle>=wait_at&&cycle<wait_end);
   int_n=!(cycle>=irq_at&&cycle<irq_at+30);nmi_n=!(cycle==nmi_at);
   #3;clk=1;#1;report(0);
   #1;if(late_mode==1 && cpu.qualified.base.tstate[3] && !mreq_n && !rd_n && a==16'h8000)late_data=1;
   #3;clk=0;#1;report(1);
  end
  $display("RESULT %0d %0d %0d",mem[32768],mem[32769],mem[32770]);
  $display("OUTPUT %0d %0d",outputs,last_output);
  $finish;
 end
 task report(input integer e);begin
  $display("PIN %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
   cycle,e,a,dout,!m1_n,!mreq_n,!iorq_n,!rd_n,!wr_n,!rfsh_n,!halt_n,!busak_n,
   address_oe,data_oe,control_oe,!wait_n,!busrq_n,
   cpu.qualified.base.mcycle,cpu.qualified.base.tstate,cpu.qualified.base.i_tv80_core.PC);
 end endtask
 always @(negedge wr_n)if(reset_n&&control_oe)begin
  if(!mreq_n)mem[a]=dout;
  if(!iorq_n)begin outputs=outputs+1;last_output=dout;end
 end
endmodule
