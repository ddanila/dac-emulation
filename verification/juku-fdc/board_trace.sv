// Observe the current reproduction without forcing additional board signals.
// The inherited juku_top_tb clock/keyboard adjuncts remain explicit limitations.
`timescale 1ns/100ps
module issue25_board_trace;
  juku_top_tb base();
  integer trace;
  initial begin
    trace=$fopen("board.csv","w");
    if (!trace) $fatal(1,"cannot open trace");
    $fwrite(trace,"ticks_100ps,address,ready,wait_cpu,iord_n,iowr_n,re_n,we_n,drq,intrq,d2,d30,d94_a4,d96,command,status,position\n");
  end
  always @(base.dut.ready or base.dut.wait_o or base.dut.iord_n or
           base.dut.iowr_n or base.dut.fdc_drq or base.dut.fdc_intrq or
           base.dut.fdc_prom_re_n or base.dut.fdc_prom_we_n) begin
    if (!base.dut.cs_fdc_n)
      $fwrite(trace,"%0t,%04x,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%02x,%02x,%0d\n",
        $time,base.dut.A,base.dut.ready,base.dut.wait_o,
        base.dut.iord_n,base.dut.iowr_n,base.dut.fdc_prom_re_n,base.dut.fdc_prom_we_n,
        base.dut.fdc_drq,base.dut.fdc_intrq,base.dut.ready_d,base.dut.d30_q,
        base.dut.d94_a4_d101_q0,base.dut.d101_d02_r92_r99,
        base.dut.U_FDC.command,base.dut.U_FDC.status,base.dut.U_FDC.buffer_pos);
  end
  final $fclose(trace);
endmodule
