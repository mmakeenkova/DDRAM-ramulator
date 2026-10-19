#pragma once

#include "ramulator/dram/commands/DDRAM_IREF.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {
template <class T>
struct IREF_B : DDRAM_IREF<T, DDRAM::VIEW_B> {};
}  // namespace Ramulator::Cmd
