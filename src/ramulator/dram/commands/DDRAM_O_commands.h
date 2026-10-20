#pragma once

#include "ramulator/dram/commands/DDRAM_PRE.h"
#include "ramulator/dram/ddram/bank_state.h"

#include <stdexcept>

namespace Ramulator::Cmd {

// Conventional access through one DDRAM-O view.  Unlike DDRAM-P, equal row
// indices in A and B are legal because intersection semantics are outside the
// milestone-one model.
template <class T, int View>
struct DDRAM_O_ACT {
  static constexpr DRAMCommandMeta meta = {.is_opening = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int, const AddrVec_t& addr_vec, Clk_t) {
    DDRAM::activate_orthogonal(bank, View, addr_vec[T::Level::Row]);
    bank->m_state = T::State::Opened;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t) {
    const int row = addr_vec[T::Level::Row];
    if (DDRAM::row_hit(bank, View, row)) {
      return cmd;
    }
    if (DDRAM::view_open(bank, View)) {
      return View == DDRAM::VIEW_A ? T::Command::PRE_A : T::Command::PRE_B;
    }
    return View == DDRAM::VIEW_A ? T::Command::ACT_A : T::Command::ACT_B;
  }
};

template <class T, int View>
struct DDRAM_O_RD {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t) {
    const int row = addr_vec[T::Level::Row];
    if (DDRAM::row_hit(bank, View, row)) {
      return cmd;
    }
    if (DDRAM::view_open(bank, View)) {
      return View == DDRAM::VIEW_A ? T::Command::PRE_A : T::Command::PRE_B;
    }
    return View == DDRAM::VIEW_A ? T::Command::ACT_A : T::Command::ACT_B;
  }

  static bool rowhit(DRAMNode* bank, int, const AddrVec_t& addr_vec, Clk_t) {
    return DDRAM::row_hit(bank, View, addr_vec[T::Level::Row]);
  }

  static bool rowopen(DRAMNode* bank, int, const AddrVec_t&, Clk_t) {
    return DDRAM::view_open(bank, View);
  }
};

template <class T, int View>
struct DDRAM_O_WR : DDRAM_O_RD<T, View> {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
};

template <class T, int View>
struct DDRAM_O_AUTO {
  static constexpr DRAMCommandMeta meta = {.is_closing = true, .is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    DDRAM_PRE<T, View>::action(bank, cmd, addr_vec, clk);
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_O_RD<T, View>::preq(bank, cmd, addr_vec, clk);
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_O_RD<T, View>::rowhit(bank, cmd, addr_vec, clk);
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return DDRAM_O_RD<T, View>::rowopen(bank, cmd, addr_vec, clk);
  }
};

// Atomic multi-row activation.  Operand representation and functional PuD
// semantics arrive in the next milestone; this command currently models bank
// occupancy and timing only and intentionally leaves no row open afterward.
template <class T, int View>
struct DDRAM_O_MRA {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int, const AddrVec_t&, Clk_t) {
    if (DDRAM::view_open(bank, View)) {
      throw std::logic_error("DDRAM-O: MRA requires its target view to be closed");
    }
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t&, Clk_t) {
    if (DDRAM::view_open(bank, View)) {
      return View == DDRAM::VIEW_A ? T::Command::PRE_A : T::Command::PRE_B;
    }
    return cmd;
  }
};

}  // namespace Ramulator::Cmd
