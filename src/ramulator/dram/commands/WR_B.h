#pragma once

#include "ramulator/dram/commands/DDRAM_WR.h"

namespace Ramulator::Cmd {

template <class T>
struct WR_B : DDRAM_WR<T, DDRAM::VIEW_B> {};

}