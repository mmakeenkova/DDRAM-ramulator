#pragma once

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

// Device-managed refresh is intentionally state-free here.  Its lock and
// duration are owned by DRAMDevice's autonomous-refresh engine; exposing a
// command descriptor makes the internal operation visible to normal tracing.
template <class T, int View>
struct DDRAM_IREF {
  static constexpr DRAMCommandMeta meta = {
      .is_refreshing = true, .is_row_command = true, .is_internal = true};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd
