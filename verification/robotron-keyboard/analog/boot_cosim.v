`timescale 1ns/1ps
// Clock/reset are analog receiver outputs; electrical matrix mode closes sense feedback.
module boot_cosim #(parameter ELECTRICAL_MATRIX=0, EXPLICIT_CPU_DRIVE=1, RESOLVED_BUS=1,
                             ELECTRICAL_OUTPUTS=0, ELECTRICAL_CPU_PULLUPS=0,
                             ELECTRICAL_LOGIC_PULLUPS=0, HOST_BUFFER=0)(input clk, input reset_n,
                  input [7:0] sense, input receiver_data, input receiver_clock,
                  input cpu_pullup_n, input bus_request_n,
                  input [2:0] logic_control,
                  output data_sink, output clock_sink,
                  output [1:0] leds, output [12:0] column_sink, output [1:0] logic_sink);
 wire [15:0] address;
 wire [10:0] rom_address;
 wire [7:0] dout, di, read_data;
 wire m1_n, mreq_n, iorq_n, rd_n, wr_n, rfsh_n, halt_n, busak_n;
 wire ta_daten, ta_takt;
 reg [7:0] rom[0:2047];
 integer cycles=0, fetches=0, reads=0, writes=0, clock_edges=0;
 initial $readmemh("s600.hex", rom);
 // Sample reset at the first external clock edge if VPI initialized the pin
 // before callbacks. Avoid an HDL timer that can advance past SPICE startup.
 reg reset_sampled=0;
 wire tied_control_n=ELECTRICAL_CPU_PULLUPS ? cpu_pullup_n : 1'b1;
 wire request_n=ELECTRICAL_CPU_PULLUPS ? bus_request_n : 1'b1;
 always @(tied_control_n or request_n) if(ELECTRICAL_CPU_PULLUPS)
  $display("CPU_CONTROL %0t %b %b", $time, tied_control_n, request_n);
 tv80n cpu(.reset_n(reset_n), .clk(clk), .wait_n(tied_control_n), .int_n(tied_control_n),
  .nmi_n(tied_control_n), .busrq_n(request_n), .di(di), .A(address), .dout(dout),
  .m1_n(m1_n), .mreq_n(mreq_n), .iorq_n(iorq_n), .rd_n(rd_n),
  .wr_n(wr_n), .rfsh_n(rfsh_n), .halt_n(halt_n), .busak_n(busak_n));
 // TV80 exposes write intent for the machine cycle independently of WR.
 // Preserve its data setup/hold window; do not derive output-enable from WR alone.
 wire cpu_data_drive=reset_n && busak_n && (EXPLICIT_CPU_DRIVE ? cpu.write : !wr_n);
 always @(logic_control) if(ELECTRICAL_LOGIC_PULLUPS)
  $display("LOGIC_CONTROL %0t %b", $time, logic_control);
 generate if(ELECTRICAL_MATRIX || EXPLICIT_CPU_DRIVE || RESOLVED_BUS || ELECTRICAL_LOGIC_PULLUPS) begin: electrical
  controller_analog #(.ELECTRICAL_LOGIC_PULLUPS(ELECTRICAL_LOGIC_PULLUPS)) board(.address(address),.cpu_data(dout),.iorq_n(iorq_n),.wr_n(wr_n),
   .logic_control(logic_control),.logic_sink(logic_sink),
   .cpu_drive(cpu_data_drive),.mreq_n(RESOLVED_BUS ? mreq_n : 1'b1),
   .rom_data(rom[rom_address]),.rom_address(rom_address),.sense(sense),.column_sink(column_sink),.read_data(read_data),.leds(leds),
   .ta_daten(ta_daten),.ta_takt(ta_takt));
 end else begin: digital
  controller board(address,dout,iorq_n,wr_n,104'b0,read_data,leds,ta_daten,ta_takt);
  assign column_sink=13'b0;
  assign rom_address=address[10:0];
  assign logic_sink=2'b00;
 end endgenerate
 assign di=RESOLVED_BUS ? read_data : (!mreq_n ? rom[address[10:0]] : read_data);
 assign data_sink=(ta_daten===1'bz || ta_daten===1'b1) ? 1'b0 : ta_daten===1'b0 ? 1'b1 : 1'bx;
 assign clock_sink=(ta_takt===1'bz || ta_takt===1'b1) ? 1'b0 : ta_takt===1'b0 ? 1'b1 : 1'bx;
 // Observe the board's transmitted intent independently of the cable receiver.
 // Both records use logical bits: the wire carries inverted data.
 // Host RxC rises when the keyboard clock collector is pulled low.
 wire transmit_event_clock = HOST_BUFFER ? ~ta_takt : ta_takt;
 always @(posedge transmit_event_clock) if(ELECTRICAL_OUTPUTS && reset_n===1'b1)
  $display("SERIAL_TX %0t %b", $time, data_sink);
 // U856 samples rising RxC (manual section 4.2.2). The cable-only
 // fixture retains its legacy release-edge transport observation.
 wire receive_event_clock = receiver_clock;
 wire receive_bit = HOST_BUFFER ? receiver_data : ~receiver_data;
 always @(posedge receive_event_clock) if(ELECTRICAL_OUTPUTS && reset_n===1'b1)
  $display("SERIAL_RX %0t %b", $time, receive_bit);
 always @(reset_n) begin
  $display("RESET %0t %b", $time, reset_n);
  if(reset_n===1'b0) begin cycles=0;fetches=0;reads=0;writes=0;end
  $fflush();
 end
 always @(posedge clk) begin
  if(!reset_sampled) begin
   $display("RESET %0t %b", $time, reset_n); $fflush(); reset_sampled=1;
  end
  clock_edges=clock_edges+1;
  if(clock_edges%100000==0) begin $display("CLOCK_PROGRESS %0t %0d",$time,clock_edges);$fflush();end
 end
 always @(posedge clk) if(reset_n===1'b1) begin
  cycles=cycles+1;
  if(!mreq_n && !m1_n && !rd_n) begin
   if(fetches==0) $display("FIRST_FETCH %0t %04x %02x",$time,address,di);
   fetches=fetches+1;
  end
  if(!iorq_n && !rd_n) reads=reads+1;
  if(!iorq_n && !wr_n) writes=writes+1;
  if(cycles%1000==0) $display("BOOT %0t %0d %0d %0d %0d %04x %b",$time,cycles,fetches,reads,writes,address,leds);
 end
endmodule
