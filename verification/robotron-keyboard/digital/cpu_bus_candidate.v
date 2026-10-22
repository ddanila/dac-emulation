// Z80 reference bus boundary, UM008011-0816 figures 5, 6 and 8.
// Values and drive enables are separate: an undriven bus is not logic zero.
// Interrupt acknowledge still uses the retained I/O candidate's base wrapper.
module cpu_bus_candidate(
 input reset_n,clk,wait_n,int_n,nmi_n,busrq_n,input [7:0] di,
 output [15:0] A,output [7:0] dout,
 output m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n,
 output address_oe,data_oe,control_oe);
 wire qmreq,qiorq,qrd,qwr,qrfsh;wire [7:0] qdata;
 tv80_io_candidate qualified(.reset_n(reset_n),.clk(clk),.wait_n(wait_n),
 .int_n(int_n),.nmi_n(nmi_n),.busrq_n(busrq_n),.di(di),.A(A),.dout(qdata),
 .m1_n(m1_n),.mreq_n(qmreq),.iorq_n(qiorq),.rd_n(qrd),.wr_n(qwr),
 .rfsh_n(qrfsh),.halt_n(halt_n),.busak_n(busak_n));
 wire fetch=qualified.base.mcycle[0] && qualified.base.intcycle_n;
 wire memory_cycle=!qualified.base.mcycle[0] && !qualified.base.iorq;
 wire reading=memory_cycle && !qualified.base.no_read && !qualified.base.write;
 wire writing=memory_cycle && qualified.base.write;
 wire t1=qualified.base.tstate[1],t2=qualified.base.tstate[2];
 wire t3=qualified.base.tstate[3],t4=qualified.base.tstate[4];
 // Register edge transitions rather than gating strobes with clk. Combinational
 // clk/state decoding can briefly reassert WR before the core's NBA state update.
 reg read_fetch=0,memory_active=0,write_active=0,refresh_active=0;
 reg [7:0] memory_data=0;
 always @(negedge clk or negedge reset_n)begin
  if(!reset_n)begin
   read_fetch<=0;memory_active<=0;write_active<=0;refresh_active<=0;memory_data<=0;
  end else begin
   read_fetch<=fetch && (t1 || t2);
   memory_active<=(reading || writing) && (t1 || t2);
   write_active<=writing && t2;
   refresh_active<=!qrfsh && t3;
   if(writing && t1)begin
    // The core's writeback mux overrides BusB for read/modify/write cycles.
    if(qualified.base.i_tv80_core.Read_To_Reg_r==5'b10110)
     memory_data<=qualified.base.i_tv80_core.Save_Mux;
    else if(qualified.base.i_tv80_core.I_RLD)
     memory_data<={qualified.base.i_tv80_core.BusB[3:0],qualified.base.i_tv80_core.BusA[3:0]};
    else if(qualified.base.i_tv80_core.I_RRD)
     memory_data<={qualified.base.i_tv80_core.BusA[3:0],qualified.base.i_tv80_core.BusB[7:4]};
    else memory_data<=qualified.base.i_tv80_core.BusB;
   end
  end
 end
 assign dout=writing?memory_data:qdata;
 assign control_oe=reset_n && busak_n;
 assign address_oe=control_oe;
 assign data_oe=control_oe && (writing || (qualified.base.iorq && qualified.base.write));
 assign rfsh_n=!control_oe || qrfsh;
 assign mreq_n=!control_oe?1'b1:
   !qrfsh?~refresh_active:fetch?~read_fetch:
   (reading || writing)?~memory_active:qmreq;
 assign rd_n=!control_oe?1'b1:!qrfsh?1'b1:
   fetch?~read_fetch:reading?~memory_active:qrd;
 assign wr_n=!control_oe?1'b1:writing?~write_active:qwr;
 assign iorq_n=(!control_oe || !qrfsh)?1'b1:qiorq;
endmodule
