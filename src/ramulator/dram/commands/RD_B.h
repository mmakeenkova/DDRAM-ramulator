#pragma once

#include "ramulator/dram/commands/DDRAM_RD.h"

namespace Ramulator::Cmd {

template <class T>
struct RD_B : DDRAM_RD<T, DDRAM::VIEW_B> {};

}