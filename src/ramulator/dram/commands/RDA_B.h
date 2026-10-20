#pragma once

#include "ramulator/dram/commands/DDRAM_RDA.h"

namespace Ramulator::Cmd {

template <class T>
struct RDA_B : DDRAM_RDA<T, DDRAM::VIEW_B> {};

}  // namespace Ramulator::Cmd
