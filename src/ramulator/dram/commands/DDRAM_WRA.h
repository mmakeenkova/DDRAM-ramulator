#pragma once

#include "ramulator/dram/commands/DDRAM_PRE.h"
#include "ramulator/dram/commands/DDRAM_WR.h"

namespace Ramulator::Cmd {

// DDRAM-P: Write through one view and auto-precharge only that view. Write
// recovery and precharge occupancy are represented by WRA-to-ACT timing.
template <class T, int View>
struct DDRAM_WRA {
  static constexpr DRAMCommandMeta meta = {.is_closing = true, .is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    DDRAM_PRE<T, View>::action(bank, cmd, addr_vec, clk);
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_WR<T, View>::preq(bank, cmd, addr_vec, clk);
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_WR<T, View>::rowhit(bank, cmd, addr_vec, clk);
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_WR<T, View>::rowopen(bank, cmd, addr_vec, clk);
  }
};

}  // namespace Ramulator::Cmd
