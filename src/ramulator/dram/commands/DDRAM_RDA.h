#pragma once

#include "ramulator/dram/commands/DDRAM_PRE.h"
#include "ramulator/dram/commands/DDRAM_RD.h"

namespace Ramulator::Cmd {

// DDRAM-P: Read through one view and start auto-precharge for that view only.
// As with the conventional RDA model, the state transition happens when the
// command issues; timing constraints keep a later ACT from using the view until
// read recovery and precharge have completed.
template <class T, int View>
struct DDRAM_RDA {
  static constexpr DRAMCommandMeta meta = {.is_closing = true, .is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    DDRAM_PRE<T, View>::action(bank, cmd, addr_vec, clk);
  }

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
