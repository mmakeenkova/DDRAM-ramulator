#pragma once

#include "ramulator/dram/commands/DDRAM_RDA.h"

namespace Ramulator::Cmd {

template <class T>
struct RDA_A : DDRAM_RDA<T, DDRAM::VIEW_A> {};

}  // namespace Ramulator::Cmd
