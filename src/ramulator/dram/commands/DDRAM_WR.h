#pragma once

#include "ramulator/dram/commands/DDRAM_RD.h"

namespace Ramulator::Cmd {

template <class T, int View>
struct DDRAM_WR {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_RD<T, View>::preq(bank, cmd, addr_vec, clk);
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_RD<T, View>::rowhit(bank, cmd, addr_vec, clk);
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_RD<T, View>::rowopen(bank, cmd, addr_vec, clk);
  }
};

}  // namespace Ramulator::Cmd