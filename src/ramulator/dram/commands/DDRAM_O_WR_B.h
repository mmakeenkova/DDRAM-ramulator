#pragma once
#include "ramulator/dram/commands/DDRAM_O_commands.h"
namespace Ramulator::Cmd { template <class T> struct DDRAM_O_WR_B : DDRAM_O_WR<T, DDRAM::VIEW_B> {}; }
