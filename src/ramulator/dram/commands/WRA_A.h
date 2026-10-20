#pragma once

#include "ramulator/dram/commands/DDRAM_WRA.h"

namespace Ramulator::Cmd {

template <class T>
struct WRA_A : DDRAM_WRA<T, DDRAM::VIEW_A> {};

}  // namespace Ramulator::Cmd
