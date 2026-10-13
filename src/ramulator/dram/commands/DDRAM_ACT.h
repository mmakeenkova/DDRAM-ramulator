#pragma once

#include "ramulator/dram/node.h"
#include "ramulator/dram/ddram/bank_state.h"
#include <stdexcept>

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

    // view hit
    if (DDRAM::row_hit(bank, View, row)) {
      return cmd;
    }

    // another row is open in this view -> close it first 
    if (DDRAM::view_open(bank, View)){
      return View == DDRAM::VIEW_A ? T::Command::PRE_A : T::Command::PRE_B;
    }

    // this view is closed, but requested row is already open in other view
    if (DDRAM::row_open_in_other_view(bank, View, row)) {
      // this is a data hazard
      throw std::logic_error("DDRAM-P: request row is open in other view");
      // fyi: this should not happen unless the controller does sth absolutely stupid and probably wrong
    }

    return View == DDRAM::VIEW_A
        ? T::Command::ACT_A
        : T::Command::ACT_B;
  }
  
};

}  // namespace Ramulator::Cmd