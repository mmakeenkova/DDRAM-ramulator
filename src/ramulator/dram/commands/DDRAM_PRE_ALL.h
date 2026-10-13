#pragma once

#include "ramulator/dram/node.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {
template <class T>
struct DDRAM_PRE_ALL {
  static constexpr DRAMCommandMeta meta = {.is_closing = true};

  static void action( DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    DDRAM::precharge_all(bank);
    bank->m_state = T::State::Closed;
  }
};
  
}  // namespace Ramulator::Cmd