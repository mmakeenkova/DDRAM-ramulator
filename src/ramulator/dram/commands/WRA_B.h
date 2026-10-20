#pragma once

#include "ramulator/dram/commands/DDRAM_WRA.h"

namespace Ramulator::Cmd {

template <class T>
struct WRA_B : DDRAM_WRA<T, DDRAM::VIEW_B> {};

}  // namespace Ramulator::Cmd
