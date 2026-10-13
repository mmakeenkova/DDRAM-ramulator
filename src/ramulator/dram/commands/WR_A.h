#pragma once

#include "ramulator/dram/commands/DDRAM_WR.h"

namespace Ramulator::Cmd {

template <class T>
struct WR_A : DDRAM_WR<T, DDRAM::VIEW_A> {};

}