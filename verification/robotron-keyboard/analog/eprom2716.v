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
