#pragma once

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

// A response emitted by an autonomous DRAM when an ACT targets a locked
// refresh region or busy sensing path.  It changes neither bank nor timing
// state; the controller models response latency before retrying.
template <class T>
struct ACT_NACK {
  static constexpr DRAMCommandMeta meta = {.is_row_command = true, .is_internal = true};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd
