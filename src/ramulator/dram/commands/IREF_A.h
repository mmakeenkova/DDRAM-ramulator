#pragma once

#include "ramulator/dram/commands/DDRAM_IREF.h"
#include "ramulator/dram/ddram/bank_state.h"

namespace Ramulator::Cmd {
template <class T>
struct IREF_A : DDRAM_IREF<T, DDRAM::VIEW_A> {};
}  // namespace Ramulator::Cmd
