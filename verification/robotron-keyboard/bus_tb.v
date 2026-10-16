`timescale 1ns/1ps
module bus_tb;
 reg [15:0] address=0;reg [7:0] cpu_data=0;reg iorq_n=1,wr_n=1;
 reg [103:0] contacts=0;wire [7:0] read_data;wire [1:0] leds;wire ta_daten,ta_takt;
 controller dut(address,cpu_data,iorq_n,wr_n,contacts,read_data,leds,ta_daten,ta_takt);
 integer f,n,kind,a,d,expected,el,ec,eb,i,count=0,failures=0;reg [1023:0] file,wave;
 initial begin
  if(!$value$plusargs("vectors=%s",file)) $fatal(1,"vectors missing");
  if($value$plusargs("wave=%s",wave))begin $dumpfile(wave);$dumpvars(0,bus_tb);end
  for(i=0;i<13;i=i+1)contacts[i*8+i%8]=1;
  f=$fopen(file,"r");if(!f)$fatal(1,"cannot open vectors");
  while(!$feof(f))begin
   n=$fscanf(f,"%d %h %h %h %h %h %h\n",kind,a,d,expected,el,ec,eb);
   if(n!=7)$fatal(1,"malformed vector");
   address=a;cpu_data=d;#5;if(kind!=2)iorq_n=0;if(kind)wr_n=0;#5;
   if(leds!==el[1:0] || (!kind && read_data!==expected[7:0]) || (kind && (ec!=1 || ta_takt!==1 || ta_daten!==!eb[0])))begin
    if(failures<12)$display("DIFF vector=%0d address=%h write=%0d read HDL=%h C=%h LEDs HDL=%h C=%h clock=%b count=%0d",count,address,kind,read_data,expected[7:0],leds,el[1:0],ta_takt,ec);
    failures=failures+1;
   end
   iorq_n=1;wr_n=1;#5;count=count+1;
  end
  $display("BUS vectors=%0d mismatches=%0d",count,failures);
  if(failures)$fatal(1,"board/emulator mismatch");$finish;
 end
endmodule
