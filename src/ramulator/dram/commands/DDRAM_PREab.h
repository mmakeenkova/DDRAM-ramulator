#pragma once

#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {

template <class T>
struct DDRAM_PREab {
  static constexpr DRAMCommandMeta meta = {.is_closing = true};
  static constexpr BankTarget bank_target = BankTarget::All;

  static void action(DRAMNode* bank, int cmd,
                     const AddrVec_t& addr_vec, Clk_t clk) {
    DDRAM::precharge_all(bank);
    bank->m_state = T::State::Closed;
    bank->m_row_state.clear();
  }
};

}  // namespace Ramulator::Cmd