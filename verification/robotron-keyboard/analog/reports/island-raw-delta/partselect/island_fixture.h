#include "vvp_island.h"
class vvp_island_tran : public vvp_island {

    public:
      void run_island() override;
      void count_drivers(vvp_island_port*port, unsigned bit_idx,
                         unsigned counts[3]) override;
};

enum tran_state_t {
      tran_disabled,
      tran_enabled,
      tran_unknown
};

struct vvp_island_branch_tran : public vvp_island_branch {

      vvp_island_branch_tran(vvp_net_t*en__, bool active_high__,
                             unsigned width__, unsigned part__,
                             unsigned offset__, bool resistive__);
      void run_test_enabled();
      bool rerun_test_enabled();
      void run_resolution();
      void run_output();

      vvp_net_t*en;
      unsigned width, part, offset;
      bool active_high, resistive;
      tran_state_t state;
};

