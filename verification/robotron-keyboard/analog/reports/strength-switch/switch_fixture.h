enum tran_state_t {
      tran_disabled,
      tran_enabled,
      tran_unknown
};
inline vvp_vector8_t resolve_ambiguous(const vvp_vector8_t&a,
                                       const vvp_vector8_t&b,
                                       tran_state_t state,
                                       const unsigned str_map[8])
{
      assert(a.size() == b.size());
      vvp_vector8_t out (a.size());

      for (unsigned idx = 0 ;  idx < out.size() ;  idx += 1) {
	    vvp_scalar_t a_bit = a.value(idx);
	    vvp_scalar_t b_bit = b.value(idx);
            b_bit = vvp_scalar_t(b_bit.value(),
                                 str_map[b_bit.strength0()],
                                 str_map[b_bit.strength1()]);
	    if (state == tran_unknown) {
		  switch (b_bit.value()) {
		      case BIT4_0:
			b_bit = vvp_scalar_t(BIT4_X, b_bit.strength0(), 0);
			break;
		      case BIT4_1:
			b_bit = vvp_scalar_t(BIT4_X, 0, b_bit.strength1());
			break;
		      default:
			break;
		  }
	    }
	    out.set_bit(idx, resolve(a_bit, b_bit));
      }
      return out;
}

