#pragma once

#include "ramulator/dram/commands/DDRAM_ACT.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT_B : DDRAM_ACT<T, DDRAM::VIEW_B> {};

}