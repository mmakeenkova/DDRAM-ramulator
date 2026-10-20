#pragma once
#include "ramulator/dram/commands/DDRAM_O_commands.h"
namespace Ramulator::Cmd { template <class T> struct DDRAM_O_WRA_A : DDRAM_O_AUTO<T, DDRAM::VIEW_A> {}; }
