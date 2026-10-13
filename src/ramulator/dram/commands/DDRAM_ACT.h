#pragma once

#include "ramulator/dram/node.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {

template <class T, int View>
struct DDRAM_ACT {
  static constexpr DRAMCommandMeta meta = {.is_opening = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec,Clk_t clk) {
    const int row = addr_vec[T::Level::Row];
    DDRAM::activate(bank, View, row);
    bank->m_state = T::State::Opened;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    const int row = addr_vec[T::Level::Row];

    // view A is closed, no need to issue PRE
    if (!DDRAM::view_open(bank, View)) {
      return cmd;
    }

    if (DDRAM::row_hit(bank, View, row)) {
      return cmd;
    }

    return View == DDRAM::VIEW_A
        ? T::Command::PRE_A
        : T::Command::PRE_B;
  }
  
};

}  // namespace Ramulator::Cmd