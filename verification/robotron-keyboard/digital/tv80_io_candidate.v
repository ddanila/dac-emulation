// Experimental Figure-7 I/O boundary. Not a production replacement.
// TV80 internal state/BusB dependencies must be qualified for every instruction
// family before adoption; interrupt acknowledge and memory use the base wrapper.
module tv80_io_candidate(
 input reset_n,clk,wait_n,int_n,nmi_n,busrq_n,input [7:0] di,
 output [15:0] A,output [7:0] dout,
 output m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n);
 wire bmreq,biorq,brd,bwr;wire [7:0] bdout;
 tv80n base(.reset_n(reset_n),.clk(clk),.wait_n(wait_n),.int_n(int_n),
 .nmi_n(nmi_n),.busrq_n(busrq_n),.di(di),.A(A),.dout(bdout),
 .m1_n(m1_n),.mreq_n(bmreq),.iorq_n(biorq),.rd_n(brd),.wr_n(bwr),
 .rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 wire io_cycle=base.iorq && !base.mcycle[0];
 reg started=0,ended=0;reg [7:0] write_data=0;
 // Data becomes available at T1 falling, before T2 rising control assertion.
 always @(negedge clk or negedge reset_n)begin
  if(!reset_n)begin ended<=0;write_data<=0;end
  else begin
   ended<=io_cycle && base.tstate[3];
   if(io_cycle && base.write && base.tstate[1] && !base.i_tv80_core.Auto_Wait_t1)
    write_data<=base.i_tv80_core.BusB;
  end
 end
 always @(posedge clk or negedge reset_n)begin
  if(!reset_n)started<=0;
  else started<=io_cycle && (base.tstate[1] || base.tstate[2]);
 end
 wire active=started && !ended && reset_n;
 assign mreq_n=io_cycle?1'b1:bmreq;
 assign iorq_n=io_cycle?~active:biorq;
 assign rd_n=io_cycle?~(active && !base.write && !base.no_read):brd;
 assign wr_n=io_cycle?~(active && base.write):bwr;
 assign dout=io_cycle && base.write?write_data:bdout;
endmodule
