#pragma once
#include "ramulator/dram/commands/DDRAM_O_commands.h"
namespace Ramulator::Cmd { template <class T> struct DDRAM_O_RD_A : DDRAM_O_RD<T, DDRAM::VIEW_A> {}; }
