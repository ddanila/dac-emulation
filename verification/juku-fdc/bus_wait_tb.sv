// Focused CPU/READY and captured-PROM contract, NOT complete board wiring.
`timescale 1ns/100ps
module issue25_bus_wait;
  reg clk=0,f1=0,f2=0,reset=1;
  wire [15:0] a;tri1 [7:0] d;
  wire sync,dbin,wr_n,wait_cpu,ready;
  reg [7:0] mem[0:65535];reg [7:0] status=0;
  reg [7:0] row=8'h80;tri1 [3:0] prom;
  integer i,waits=0,reads=0,writes=0;
  reg [4:0] decode=31;tri1 [7:0] strobes;reg [7:0] captured[0:31];
  wait_prom_037 d2(.a(row),.v1_n(1'b0),.v2_n(1'b0),.d(prom));
  tm2_dff #(.FUNCTIONAL(1)) d30(.d1(prom[0]),.clk1(f2),.clr1_n(1'b1),.pre1_n(1'b1),
    .q1(ready),.q1_n(),.d2(1'b0),.clk2(1'b0),.clr2_n(1'b1),.pre2_n(1'b1),.q2(),.q2_n());
  re3_prom_092 d94(.a(decode),.e_n(1'b0),.d(strobes));
  cpu_8080 cpu(.sclk(clk),.phi1(f1),.phi2(f2),.ready(ready),.reset(reset),.hold(1'b0),.intr(1'b0),
    .vss_gnd(1'b0),.vbb_m5v(1'b0),.vcc_5v(1'b1),.vdd_12v(1'b1),
    .A(a),.D(d),.dbin(dbin),.wr_n(wr_n),.sync(sync),.hlda(),.inte(),.wait_o(wait_cpu));
  initial forever begin
    f1=1;clk=0;#10;clk=1;#10;f1=0;f2=1;clk=0;#10;clk=1;#10;f2=0;
  end
  always @(posedge clk) if(sync)status=d;
  assign d=dbin ? (status[6]?8'ha7:mem[a]):8'hzz;
  always @(posedge f2) if(wait_cpu)waits=waits+1;
  // Hold the PROM in its captured READY-low row during each I/O. This is
  // deliberate external stimulus; the board's source of that row is not inferred.
  always @(posedge sync) begin
    #1;
    if(d[6] || d[4]) begin row=0;#800;row=8'h80;end
  end
  always @(negedge dbin) if(status[6])reads=reads+1;
  always @(negedge wr_n) begin
    if(status[4]) begin
      if(d!==8'ha7)$fatal(1,"OUT payload changed");
      writes=writes+1;
    end else begin
      mem[a]=d;
      if(a==16'h4000) begin
        if(d!==8'ha7 || reads!=1 || writes!=1 || waits<10)$fatal(1,"I/O wait/commit failure");
        $display("VM80A PROM READY: PASS reads=%0d writes=%0d wait_phases=%0d",reads,writes,waits);$finish;
      end
    end
  end
  initial begin
    $readmemh("ref/physical-proms/validated/d94_092.raw.hex",captured);
    for(i=0;i<32;i=i+1)begin decode=i;#1;if(strobes!==captured[i])$fatal(1,"D94 table mismatch row=%d got=%h expected=%h",i,strobes,captured[i]);end
    decode=5'h0b;#1;if(strobes[2]!==1)$fatal(1,"A4 low must inhibit data read");
    decode=5'h1b;#1;if(strobes[2]!==0)$fatal(1,"A4 high must allow data read");
    decode=5'h07;#1;if(strobes[3]!==1)$fatal(1,"A4 low must inhibit data write");
    decode=5'h17;#1;if(strobes[3]!==0)$fatal(1,"A4 high must allow data write");
    for(i=0;i<65536;i=i+1)mem[i]=0;
    mem[0]=8'hdb;mem[1]=8'h1f;mem[2]=8'hd3;mem[3]=8'h1f;
    mem[4]=8'h32;mem[5]=0;mem[6]=8'h40;mem[7]=8'h76;
    #2000;reset=0;
  end
  initial begin #100000;$fatal(1,"CPU wait timeout");end
endmodule
