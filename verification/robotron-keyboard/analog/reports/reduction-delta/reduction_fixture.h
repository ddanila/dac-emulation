#include "vvp_net.h"
class vvp_reduce_base : public vvp_net_fun_t {

    public:
      vvp_reduce_base();
      int robotron_reduction_inventory(FILE*) const;
      int robotron_reduction_toggle(int);
      virtual ~vvp_reduce_base() override;

      void recv_vec4(vvp_net_ptr_t prt, const vvp_vector4_t&bit,
                     vvp_context_t context) override;
      void recv_vec4_pv(vvp_net_ptr_t ptr, const vvp_vector4_t&bit,
			unsigned base, unsigned vwid, vvp_context_t context) override;

      virtual vvp_bit4_t calculate_result() const =0;

    protected:
      vvp_vector4_t bits_;
};
class vvp_reduce_and  : public vvp_reduce_base {

    public:
      vvp_reduce_and();
      ~vvp_reduce_and() override;
      vvp_bit4_t calculate_result() const override;
};
class vvp_reduce_or  : public vvp_reduce_base {

    public:
      vvp_reduce_or();
      ~vvp_reduce_or() override;
      vvp_bit4_t calculate_result() const override;
};
class vvp_reduce_xor  : public vvp_reduce_base {

    public:
      vvp_reduce_xor();
      ~vvp_reduce_xor() override;
      vvp_bit4_t calculate_result() const override;
};
class vvp_reduce_nand  : public vvp_reduce_base {

    public:
      vvp_reduce_nand();
      ~vvp_reduce_nand() override;
      vvp_bit4_t calculate_result() const override;
};
class vvp_reduce_nor  : public vvp_reduce_base {

    public:
      vvp_reduce_nor();
      ~vvp_reduce_nor() override;
      vvp_bit4_t calculate_result() const override;
};
class vvp_reduce_xnor  : public vvp_reduce_base {

    public:
      vvp_reduce_xnor();
      ~vvp_reduce_xnor() override;
      vvp_bit4_t calculate_result() const override;
};
