// Generated from reference/connectivity.json SHA256 68ce8ebda5a03cb5d5339b78b2e964ed3c2b2fdfee379f77029d9f38e128aa25
module controller_electrical_bus #(parameter ELECTRICAL_LOGIC_PULLUPS=0)(input [15:0] address, input [7:0] cpu_data,
 input iorq_n, wr_n, input cpu_drive, input mreq_n, input [7:0] rom_data, output [10:0] rom_address, input [7:0] bus_sense, output [23:0] bus_low, bus_high, input [7:0] sense, output [12:0] column_sink, input [2:0] logic_control, output [1:0] logic_sink,
 output [7:0] read_data, output [1:0] leds,
 output ta_daten, ta_takt);
wire [7:0] cpu_driver, rom_driver, latch_driver, rom_timed;

wire n__5V;
wire n_A0;
wire n_A1;
wire n_A10;
wire n_A11;
wire n_A12;
wire n_A13;
wire n_A14;
wire n_A15;
wire n_A2;
wire n_A3;
wire n_A4;
wire n_A5;
wire n_A6;
wire n_A7;
wire n_A8;
wire n_A9;
wire n_BASE0;
wire n_BASE1;
wire n_BASE2;
wire n_BASE3;
wire n_BASE4;
wire n_BASE5;
wire n_BASE6;
wire n_BASE7;
wire n_BUSRQ_N;
wire n_CABLE_5V;
wire n_CABLE_DATEN;
wire n_CABLE_GND;
wire n_CABLE_TAKT;
wire n_CLK;
wire n_COL0;
wire n_COL1;
wire n_COL10;
wire n_COL11;
wire n_COL12;
wire n_COL2;
wire n_COL3;
wire n_COL4;
wire n_COL5;
wire n_COL6;
wire n_COL7;
wire n_COL8;
wire n_COL9;
wire n_CPU_PULLUP;
wire n_D0;
wire n_D1;
wire n_D2;
wire n_D3;
wire n_D4;
wire n_D5;
wire n_D6;
wire n_D7;
wire n_FF_PULLUP;
wire n_GND;
wire n_IORQ_N;
wire n_IO_ACTIVE;
wire n_LATCH_OE_N;
wire n_LED_CAPS;
wire n_LED_CAPS_N;
wire n_LED_SISO;
wire n_LED_SISO_N;
wire n_MREQ_N;
wire n_OSC1;
wire n_OSC2;
wire n_OSC_OUT;
wire n_OSC_RC;
wire n_RD_N;
wire n_RESET_BASE;
wire n_RESET_BIAS;
wire n_RESET_BIAS_LOW;
wire n_RESET_DIODE_TOP;
wire n_RESET_EMITTERS;
wire n_RESET_N;
wire n_RESET_OUT;
wire n_RESET_RC;
wire n_ROW0;
wire n_ROW1;
wire n_ROW2;
wire n_ROW3;
wire n_ROW4;
wire n_ROW5;
wire n_ROW6;
wire n_ROW7;
wire n_SENSE0;
wire n_SENSE1;
wire n_SENSE2;
wire n_SENSE3;
wire n_SENSE4;
wire n_SENSE5;
wire n_SENSE6;
wire n_SENSE7;
wire n_SHIELD;
wire n_TA_DATEN;
wire n_TA_TAKT;
wire n_WR_N;
assign n__5V=1'b1;
assign n_GND=1'b0;
assign n_A0=address[0];
assign n_A1=address[1];
assign n_A2=address[2];
assign n_A3=address[3];
assign n_A4=address[4];
assign n_A5=address[5];
assign n_A6=address[6];
assign n_A7=address[7];
assign n_A8=address[8];
assign n_A9=address[9];
assign n_A10=address[10];
assign n_A11=address[11];
assign n_A12=address[12];
assign n_A13=address[13];
assign n_A14=address[14];
assign n_A15=address[15];
assign cpu_driver[0]=cpu_drive ? cpu_data[0] : 1'bz;
assign read_data[0]=n_D0;
assign n_D0=bus_sense[0];
assign cpu_driver[1]=cpu_drive ? cpu_data[1] : 1'bz;
assign read_data[1]=n_D1;
assign n_D1=bus_sense[1];
assign cpu_driver[2]=cpu_drive ? cpu_data[2] : 1'bz;
assign read_data[2]=n_D2;
assign n_D2=bus_sense[2];
assign cpu_driver[3]=cpu_drive ? cpu_data[3] : 1'bz;
assign read_data[3]=n_D3;
assign n_D3=bus_sense[3];
assign cpu_driver[4]=cpu_drive ? cpu_data[4] : 1'bz;
assign read_data[4]=n_D4;
assign n_D4=bus_sense[4];
assign cpu_driver[5]=cpu_drive ? cpu_data[5] : 1'bz;
assign read_data[5]=n_D5;
assign n_D5=bus_sense[5];
assign cpu_driver[6]=cpu_drive ? cpu_data[6] : 1'bz;
assign read_data[6]=n_D6;
assign n_D6=bus_sense[6];
assign cpu_driver[7]=cpu_drive ? cpu_data[7] : 1'bz;
assign read_data[7]=n_D7;
assign n_D7=bus_sense[7];
assign n_IORQ_N=iorq_n;
assign n_WR_N=wr_n;
pullup(n_TA_TAKT);
pullup(n_TA_DATEN);
pullup(n_CLK);
pullup(n_RESET_BIAS_LOW);
pullup(n_RESET_DIODE_TOP);
pullup(n_RESET_BIAS);
pullup(n_RESET_BASE);
generate if(!ELECTRICAL_LOGIC_PULLUPS) begin: pullup_latchEnable
 pullup(n_LATCH_OE_N);
end endgenerate
pullup(n_CPU_PULLUP);
pullup(n_BUSRQ_N);
generate if(!ELECTRICAL_LOGIC_PULLUPS) begin: pullup_flipFlopRelease
 pullup(n_FF_PULLUP);
end endgenerate
generate if(!ELECTRICAL_LOGIC_PULLUPS) begin: pullup_ioActive
 pullup(n_IO_ACTIVE);
end endgenerate
pullup(n_COL0);
pullup(n_COL1);
pullup(n_COL2);
pullup(n_COL3);
pullup(n_COL4);
pullup(n_COL5);
pullup(n_COL6);
pullup(n_COL7);
pullup(n_COL8);
pullup(n_COL9);
pullup(n_COL10);
pullup(n_COL11);
pullup(n_COL12);
assign n_SENSE0=sense[0];
assign n_SENSE1=sense[1];
assign n_SENSE2=sense[2];
assign n_SENSE3=sense[3];
assign n_SENSE4=sense[4];
assign n_SENSE5=sense[5];
assign n_SENSE6=sense[6];
assign n_SENSE7=sense[7];
chip_7406 A1(.p1(n_WR_N),.p2(n_TA_TAKT),.p3(n_D0),.p4(n_TA_DATEN),.p5(),.p6(),.p7(n_GND),.p8(n_COL1),.p9(n_A1),.p10(n_COL6),.p11(n_A6),.p12(n_COL4),.p13(n_A4),.p14(n__5V));
chip_DL003 A2_1(.p1(n_A3),.p2(n_A3),.p3(n_COL3),.p4(n_A11),.p5(n_A11),.p6(n_COL11),.p7(n_GND),.p8(n_COL2),.p9(n_A2),.p10(n_A2),.p11(n_COL5),.p12(n_A5),.p13(n_A5),.p14(n__5V));
wire control_driver_latchEnable;
wire control_driver_ioActive;
chip_DL003 A2_2(.p1(n_A7),.p2(n_A7),.p3(n_COL7),.p4(n_IORQ_N),.p5(n_IORQ_N),.p6(control_driver_ioActive),.p7(n_GND),.p8(control_driver_latchEnable),.p9(n_A15),.p10(n_A15),.p11(n_COL12),.p12(n_A12),.p13(n_A12),.p14(n__5V));
chip_DL003 A2_3(.p1(n_A10),.p2(n_A10),.p3(n_COL10),.p4(n_A9),.p5(n_A9),.p6(n_COL9),.p7(n_GND),.p8(n_COL0),.p9(n_A0),.p10(n_A0),.p11(n_COL8),.p12(n_A8),.p13(n_A8),.p14(n__5V));
chip_I8282 A4(.p1(n_SENSE0),.p2(n_SENSE1),.p3(n_SENSE2),.p4(n_SENSE3),.p5(n_SENSE4),.p6(n_SENSE5),.p7(n_SENSE6),.p8(n_SENSE7),.p9(n_LATCH_OE_N),.p10(n_GND),.p11(n_IO_ACTIVE),.p12(latch_driver[7]),.p13(latch_driver[6]),.p14(latch_driver[5]),.p15(latch_driver[4]),.p16(latch_driver[3]),.p17(latch_driver[2]),.p18(latch_driver[1]),.p19(latch_driver[0]),.p20(n__5V));
chip_DL074 A6(.p1(n_FF_PULLUP),.p2(n_A14),.p3(n_IO_ACTIVE),.p4(n_FF_PULLUP),.p5(),.p6(n_LED_CAPS_N),.p7(n_GND),.p8(n_LED_SISO_N),.p9(),.p10(n_FF_PULLUP),.p11(n_IO_ACTIVE),.p12(n_A13),.p13(n_FF_PULLUP),.p14(n__5V));
assign leds={~n_LED_CAPS_N,~n_LED_SISO_N};
assign ta_daten=n_TA_DATEN;
assign ta_takt=n_TA_TAKT;
assign logic_sink[0]=control_driver_latchEnable===1'b0 ? 1'b1 : (control_driver_latchEnable===1'b1 || control_driver_latchEnable===1'bz) ? 1'b0 : 1'bx;
assign n_LATCH_OE_N=ELECTRICAL_LOGIC_PULLUPS ? logic_control[0] : control_driver_latchEnable;
assign n_FF_PULLUP=ELECTRICAL_LOGIC_PULLUPS ? logic_control[1] : 1'bz;
assign logic_sink[1]=control_driver_ioActive===1'b0 ? 1'b1 : (control_driver_ioActive===1'b1 || control_driver_ioActive===1'bz) ? 1'b0 : 1'bx;
assign n_IO_ACTIVE=ELECTRICAL_LOGIC_PULLUPS ? logic_control[2] : control_driver_ioActive;
assign n_MREQ_N=mreq_n;
assign rom_address[0]=n_A0;
assign rom_address[1]=n_A1;
assign rom_address[2]=n_A2;
assign rom_address[3]=n_A3;
assign rom_address[4]=n_A4;
assign rom_address[5]=n_A5;
assign rom_address[6]=n_A6;
assign rom_address[7]=n_A7;
assign rom_address[8]=n_A8;
assign rom_address[9]=n_A9;
assign rom_address[10]=n_A10;
assign rom_driver[0]=rom_timed[0];
assign rom_driver[1]=rom_timed[1];
assign rom_driver[2]=rom_timed[2];
assign rom_driver[3]=rom_timed[3];
assign rom_driver[4]=rom_timed[4];
assign rom_driver[5]=rom_timed[5];
assign rom_driver[6]=rom_timed[6];
assign rom_driver[7]=rom_timed[7];
assign column_sink[0]=n_COL0===1'b0 ? 1'b1 : (n_COL0===1'b1 || n_COL0===1'bz) ? 1'b0 : 1'bx;
assign column_sink[1]=n_COL1===1'b0 ? 1'b1 : (n_COL1===1'b1 || n_COL1===1'bz) ? 1'b0 : 1'bx;
assign column_sink[2]=n_COL2===1'b0 ? 1'b1 : (n_COL2===1'b1 || n_COL2===1'bz) ? 1'b0 : 1'bx;
assign column_sink[3]=n_COL3===1'b0 ? 1'b1 : (n_COL3===1'b1 || n_COL3===1'bz) ? 1'b0 : 1'bx;
assign column_sink[4]=n_COL4===1'b0 ? 1'b1 : (n_COL4===1'b1 || n_COL4===1'bz) ? 1'b0 : 1'bx;
assign column_sink[5]=n_COL5===1'b0 ? 1'b1 : (n_COL5===1'b1 || n_COL5===1'bz) ? 1'b0 : 1'bx;
assign column_sink[6]=n_COL6===1'b0 ? 1'b1 : (n_COL6===1'b1 || n_COL6===1'bz) ? 1'b0 : 1'bx;
assign column_sink[7]=n_COL7===1'b0 ? 1'b1 : (n_COL7===1'b1 || n_COL7===1'bz) ? 1'b0 : 1'bx;
assign column_sink[8]=n_COL8===1'b0 ? 1'b1 : (n_COL8===1'b1 || n_COL8===1'bz) ? 1'b0 : 1'bx;
assign column_sink[9]=n_COL9===1'b0 ? 1'b1 : (n_COL9===1'b1 || n_COL9===1'bz) ? 1'b0 : 1'bx;
assign column_sink[10]=n_COL10===1'b0 ? 1'b1 : (n_COL10===1'b1 || n_COL10===1'bz) ? 1'b0 : 1'bx;
assign column_sink[11]=n_COL11===1'b0 ? 1'b1 : (n_COL11===1'b1 || n_COL11===1'bz) ? 1'b0 : 1'bx;
assign column_sink[12]=n_COL12===1'b0 ? 1'b1 : (n_COL12===1'b1 || n_COL12===1'bz) ? 1'b0 : 1'bx;
assign bus_low[0]=(cpu_driver[0]===1'bz) ? 1'b0 : (cpu_driver[0]===1'b0) ? 1'b1 : (cpu_driver[0]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[0]=(cpu_driver[0]===1'bz) ? 1'b0 : (cpu_driver[0]===1'b1) ? 1'b1 : (cpu_driver[0]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[8]=(rom_driver[0]===1'bz) ? 1'b0 : (rom_driver[0]===1'b0) ? 1'b1 : (rom_driver[0]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[8]=(rom_driver[0]===1'bz) ? 1'b0 : (rom_driver[0]===1'b1) ? 1'b1 : (rom_driver[0]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[16]=(latch_driver[0]===1'bz) ? 1'b0 : (latch_driver[0]===1'b0) ? 1'b1 : (latch_driver[0]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[16]=(latch_driver[0]===1'bz) ? 1'b0 : (latch_driver[0]===1'b1) ? 1'b1 : (latch_driver[0]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[1]=(cpu_driver[1]===1'bz) ? 1'b0 : (cpu_driver[1]===1'b0) ? 1'b1 : (cpu_driver[1]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[1]=(cpu_driver[1]===1'bz) ? 1'b0 : (cpu_driver[1]===1'b1) ? 1'b1 : (cpu_driver[1]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[9]=(rom_driver[1]===1'bz) ? 1'b0 : (rom_driver[1]===1'b0) ? 1'b1 : (rom_driver[1]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[9]=(rom_driver[1]===1'bz) ? 1'b0 : (rom_driver[1]===1'b1) ? 1'b1 : (rom_driver[1]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[17]=(latch_driver[1]===1'bz) ? 1'b0 : (latch_driver[1]===1'b0) ? 1'b1 : (latch_driver[1]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[17]=(latch_driver[1]===1'bz) ? 1'b0 : (latch_driver[1]===1'b1) ? 1'b1 : (latch_driver[1]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[2]=(cpu_driver[2]===1'bz) ? 1'b0 : (cpu_driver[2]===1'b0) ? 1'b1 : (cpu_driver[2]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[2]=(cpu_driver[2]===1'bz) ? 1'b0 : (cpu_driver[2]===1'b1) ? 1'b1 : (cpu_driver[2]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[10]=(rom_driver[2]===1'bz) ? 1'b0 : (rom_driver[2]===1'b0) ? 1'b1 : (rom_driver[2]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[10]=(rom_driver[2]===1'bz) ? 1'b0 : (rom_driver[2]===1'b1) ? 1'b1 : (rom_driver[2]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[18]=(latch_driver[2]===1'bz) ? 1'b0 : (latch_driver[2]===1'b0) ? 1'b1 : (latch_driver[2]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[18]=(latch_driver[2]===1'bz) ? 1'b0 : (latch_driver[2]===1'b1) ? 1'b1 : (latch_driver[2]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[3]=(cpu_driver[3]===1'bz) ? 1'b0 : (cpu_driver[3]===1'b0) ? 1'b1 : (cpu_driver[3]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[3]=(cpu_driver[3]===1'bz) ? 1'b0 : (cpu_driver[3]===1'b1) ? 1'b1 : (cpu_driver[3]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[11]=(rom_driver[3]===1'bz) ? 1'b0 : (rom_driver[3]===1'b0) ? 1'b1 : (rom_driver[3]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[11]=(rom_driver[3]===1'bz) ? 1'b0 : (rom_driver[3]===1'b1) ? 1'b1 : (rom_driver[3]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[19]=(latch_driver[3]===1'bz) ? 1'b0 : (latch_driver[3]===1'b0) ? 1'b1 : (latch_driver[3]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[19]=(latch_driver[3]===1'bz) ? 1'b0 : (latch_driver[3]===1'b1) ? 1'b1 : (latch_driver[3]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[4]=(cpu_driver[4]===1'bz) ? 1'b0 : (cpu_driver[4]===1'b0) ? 1'b1 : (cpu_driver[4]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[4]=(cpu_driver[4]===1'bz) ? 1'b0 : (cpu_driver[4]===1'b1) ? 1'b1 : (cpu_driver[4]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[12]=(rom_driver[4]===1'bz) ? 1'b0 : (rom_driver[4]===1'b0) ? 1'b1 : (rom_driver[4]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[12]=(rom_driver[4]===1'bz) ? 1'b0 : (rom_driver[4]===1'b1) ? 1'b1 : (rom_driver[4]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[20]=(latch_driver[4]===1'bz) ? 1'b0 : (latch_driver[4]===1'b0) ? 1'b1 : (latch_driver[4]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[20]=(latch_driver[4]===1'bz) ? 1'b0 : (latch_driver[4]===1'b1) ? 1'b1 : (latch_driver[4]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[5]=(cpu_driver[5]===1'bz) ? 1'b0 : (cpu_driver[5]===1'b0) ? 1'b1 : (cpu_driver[5]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[5]=(cpu_driver[5]===1'bz) ? 1'b0 : (cpu_driver[5]===1'b1) ? 1'b1 : (cpu_driver[5]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[13]=(rom_driver[5]===1'bz) ? 1'b0 : (rom_driver[5]===1'b0) ? 1'b1 : (rom_driver[5]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[13]=(rom_driver[5]===1'bz) ? 1'b0 : (rom_driver[5]===1'b1) ? 1'b1 : (rom_driver[5]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[21]=(latch_driver[5]===1'bz) ? 1'b0 : (latch_driver[5]===1'b0) ? 1'b1 : (latch_driver[5]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[21]=(latch_driver[5]===1'bz) ? 1'b0 : (latch_driver[5]===1'b1) ? 1'b1 : (latch_driver[5]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[6]=(cpu_driver[6]===1'bz) ? 1'b0 : (cpu_driver[6]===1'b0) ? 1'b1 : (cpu_driver[6]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[6]=(cpu_driver[6]===1'bz) ? 1'b0 : (cpu_driver[6]===1'b1) ? 1'b1 : (cpu_driver[6]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[14]=(rom_driver[6]===1'bz) ? 1'b0 : (rom_driver[6]===1'b0) ? 1'b1 : (rom_driver[6]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[14]=(rom_driver[6]===1'bz) ? 1'b0 : (rom_driver[6]===1'b1) ? 1'b1 : (rom_driver[6]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[22]=(latch_driver[6]===1'bz) ? 1'b0 : (latch_driver[6]===1'b0) ? 1'b1 : (latch_driver[6]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[22]=(latch_driver[6]===1'bz) ? 1'b0 : (latch_driver[6]===1'b1) ? 1'b1 : (latch_driver[6]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[7]=(cpu_driver[7]===1'bz) ? 1'b0 : (cpu_driver[7]===1'b0) ? 1'b1 : (cpu_driver[7]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[7]=(cpu_driver[7]===1'bz) ? 1'b0 : (cpu_driver[7]===1'b1) ? 1'b1 : (cpu_driver[7]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[15]=(rom_driver[7]===1'bz) ? 1'b0 : (rom_driver[7]===1'b0) ? 1'b1 : (rom_driver[7]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[15]=(rom_driver[7]===1'bz) ? 1'b0 : (rom_driver[7]===1'b1) ? 1'b1 : (rom_driver[7]===1'b0) ? 1'b0 : 1'bx;
assign bus_low[23]=(latch_driver[7]===1'bz) ? 1'b0 : (latch_driver[7]===1'b0) ? 1'b1 : (latch_driver[7]===1'b1) ? 1'b0 : 1'bx;
assign bus_high[23]=(latch_driver[7]===1'bz) ? 1'b0 : (latch_driver[7]===1'b1) ? 1'b1 : (latch_driver[7]===1'b0) ? 1'b0 : 1'bx;
eprom2716_read_envelope rom_access(.address(rom_address),.data(rom_data),.ce_n(n_GND),.oe_n(n_MREQ_N),.q(rom_timed));
endmodule

`timescale 1ns/1ps
// Intel 2716 read envelope, standard 450 ns grade, printed page 2-5:
// https://www.theoddys.com/acorn/semiconductor_datasheets/2716%20Intel.pdf
// PDF SHA256: 2c05fb7079c29c9457897a57f63f175a2187d8a1a5dfce9cc3dc04db4a0c47c2
// Limits assume 5 V +/-5%, 0..70 C, one TTL gate +100 pF, input edges <=20 ns.
// X denotes an unspecified interval, not a predicted physical voltage. This
// conservative digital envelope is not a U556 calibration or an analog I/V model.
// Programming, brownout and supply sequencing are outside this read-only model.
module eprom2716_read_envelope(
 input [10:0] address, input [7:0] data,
 input ce_n, oe_n, output [7:0] q
);
 integer address_epoch=0, ce_epoch=0, oe_epoch=0;
 integer address_ready=-1, ce_ready=-1, oe_ready=-1;
 // Constant pins need an initial settling event even without a time-zero edge.
 initial begin
  #0;
  address_ready <= #450 address_epoch;
  ce_ready <= #450 ce_epoch;
  oe_ready <= #120 oe_epoch;
 end
 // Epochs prevent an older delayed event (including A->B->A glitches) from
 // declaring a newer access valid. Nonblocking delayed updates retain events.
 always @(address) begin
  address_epoch=address_epoch+1;
  address_ready <= #450 address_epoch;
 end
 always @(ce_n) begin
  ce_epoch=ce_epoch+1;
  ce_ready <= #450 ce_epoch;
 end
 always @(oe_n) begin
  oe_epoch=oe_epoch+1;
  oe_ready <= #120 oe_epoch;
 end
 wire disabled=(ce_n===1'b1 || oe_n===1'b1);
 wire released;
 // Either disable starts tDF; changes to the other disabled control do not
 // restart it. Inertial delay rejects a disable pulse shorter than tDF.
 assign #100 released=disabled;
 wire valid=(ce_n===1'b0 && oe_n===1'b0 && (^address)!==1'bx &&
             address_epoch==address_ready && ce_epoch==ce_ready && oe_epoch==oe_ready);
 // No positive hold-time guarantee: data becomes unspecified immediately.
 assign q=disabled ? (released===1'b1 ? 8'bzzzzzzzz : 8'bxxxxxxxx) :
          valid ? data : 8'bxxxxxxxx;
endmodule

`timescale 1ns/1ps
// Clock/reset are analog receiver outputs; electrical matrix mode closes sense feedback.
module boot_electrical_bus #(parameter ELECTRICAL_MATRIX=0, EXPLICIT_CPU_DRIVE=1, RESOLVED_BUS=1,
                             ELECTRICAL_OUTPUTS=0, ELECTRICAL_CPU_PULLUPS=0,
                             ELECTRICAL_LOGIC_PULLUPS=0)(input clk, input reset_n,
                  input [7:0] sense, input receiver_data, input receiver_clock,
                  input cpu_pullup_n, input bus_request_n,
                  input [2:0] logic_control,
                  input [7:0] bus_sense, output [23:0] bus_low, bus_high, output data_sink, output clock_sink,
                  output [1:0] leds, output [12:0] column_sink, output [1:0] logic_sink);
 wire [15:0] address;
 wire [10:0] rom_address;
 wire [7:0] dout, di, read_data;
 wire m1_n, mreq_n, iorq_n, rd_n, wr_n, rfsh_n, halt_n, busak_n;
 wire ta_daten, ta_takt;
 reg [7:0] rom[0:2047];
 integer cycles=0, fetches=0, reads=0, writes=0, clock_edges=0;
 initial if(!RESOLVED_BUS || !EXPLICIT_CPU_DRIVE || !ELECTRICAL_MATRIX)
  $fatal(1,"Electrical bus requires resolved ROM, CPU drive intent and matrix feedback");
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
  controller_electrical_bus #(.ELECTRICAL_LOGIC_PULLUPS(ELECTRICAL_LOGIC_PULLUPS)) board(.address(address),.cpu_data(dout),.iorq_n(iorq_n),.wr_n(wr_n),
   .bus_sense(bus_sense),.bus_low(bus_low),.bus_high(bus_high),
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
 always @(posedge ta_takt) if(ELECTRICAL_OUTPUTS && reset_n===1'b1)
  $display("SERIAL_TX %0t %b", $time, data_sink);
 always @(posedge receiver_clock) if(ELECTRICAL_OUTPUTS && reset_n===1'b1)
  $display("SERIAL_RX %0t %b", $time, ~receiver_data);
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
reg [7:0] bus_sample_value;
 always @(posedge clk or negedge clk) begin
  if(reset_n===1'b1 && ((clk===1'b1 && cpu.mcycle[0]===1'b1 &&
       cpu.tstate[2]===1'b1 && cpu.wait_n===1'b1) ||
      (clk===1'b0 && cpu.delayed_read===1'b1)) &&
     rd_n===1'b0 && (mreq_n===1'b0 || iorq_n===1'b0)) begin
   $display("BUS_SAMPLE %0t %04x %02x %b %b %b",$time,address,di,mreq_n,iorq_n,m1_n);
   bus_sample_value <= di;
   // Postponed-region observation sees the completed nonblocking input latch.
   // It must not depend on a later clock edge outside the capture interval.
   $strobe("BUS_LATCH %0t %02x %02x",$time,bus_sample_value,cpu.di_reg);
  end
 end
endmodule

`timescale 1ns/1ps
// Service fixture: BR1/BR2 open, external 1 MHz clock and reset at CPU-side pins.
// The board oscillator/reset generator is outside this focused I/O experiment.
module firmware_io_electrical_bus #(parameter ELECTRICAL_LOGIC_PULLUPS=0, ELECTRICAL_CPU_PULLUPS=0)(input fixture_clk, fixture_reset_n,
                         input [7:0] sense, input receiver_data, receiver_clock,
                         input [2:0] logic_control, input cpu_pullup_n, bus_request_n,
                         input [7:0] bus_sense, output [23:0] bus_low, bus_high, output [1:0] logic_sink,
                         output data_sink, clock_sink, output [1:0] leds,
                         output [12:0] column_sink);
 wire clk, reset_n;
 controller_service service_boundary(.oscillator(1'b0),.reset_source_n(1'b1),
  .br1_closed(1'b0),.br2_closed(1'b0),.external_clk(fixture_clk),
  .external_reset_n(fixture_reset_n),.cpu_clk(clk),.cpu_reset_n(reset_n));
 boot_electrical_bus #(.ELECTRICAL_MATRIX(1),.ELECTRICAL_OUTPUTS(1),
  .ELECTRICAL_LOGIC_PULLUPS(ELECTRICAL_LOGIC_PULLUPS),
  .ELECTRICAL_CPU_PULLUPS(ELECTRICAL_CPU_PULLUPS)) board(
  .clk(clk),.reset_n(reset_n),.sense(sense),.receiver_data(receiver_data),
  .receiver_clock(receiver_clock),.data_sink(data_sink),.clock_sink(clock_sink),
  .cpu_pullup_n(cpu_pullup_n),.bus_request_n(bus_request_n),
  .bus_sense(bus_sense),.bus_low(bus_low),.bus_high(bus_high),
  .logic_control(logic_control),.logic_sink(logic_sink),
  .leds(leds),.column_sink(column_sink));
endmodule
