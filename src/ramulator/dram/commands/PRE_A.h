#pragma once

#include "ramulator/dram/commands/DDRAM_PRE.h"

namespace Ramulator::Cmd {

template <class T>
struct PRE_A : DDRAM_PRE<T, DDRAM::VIEW_A> {};

}