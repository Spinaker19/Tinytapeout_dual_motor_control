# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info
#
# Usage (run from inside the LibreLane nix-shell):
#   make -B            — functional tests (9 tests, rtmc_tests.py)
#   make -B SCAN=yes   — DFT scan chain tests (3 tests, rtmc_scan_test.py)
#   make -B GATES=yes  — gate-level simulation (requires gate_level_netlist.v)

# defaults
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = tt_um_rtmc_top_jrpetrus.sv rtmc_spi_rxtx.sv rtmc_spi.sv rtmc_core.sv rtmc_ctrl.sv

ifneq ($(SCAN),yes)
ifneq ($(GATES),yes)

# RTL simulation (default):
SIM_BUILD			= sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
COMPILE_ARGS 		+= -I$(SRC_DIR)

ifeq ($(SIM),verilator)
COMPILE_ARGS += --trace
endif

else

# Gate level simulation:
SIM_BUILD		 = sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DUSE_POWER_PINS
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DUNIT_DELAY=\#1
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v
endif

# Include the testbench sources:
VERILOG_SOURCES += $(SRC_DIR)/rtmc_pkg.sv
VERILOG_SOURCES += $(SRC_DIR)/rtmc_interfaces.sv
VERILOG_SOURCES += $(PWD)/rtmc_tb.sv

TOPLEVEL = rtmc_tb
MODULE   = rtmc_tests

else

# Scan chain simulation (make -B SCAN=yes):
# Tests the 373-bit MUX-D scan chain inserted in the RTL.
# Uses the same rtmc_tb testbench top-level (scan pins are exposed via ui_in/uo_out).
SIM_BUILD        = sim_build/scan
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
VERILOG_SOURCES += $(SRC_DIR)/rtmc_pkg.sv
VERILOG_SOURCES += $(SRC_DIR)/rtmc_interfaces.sv
VERILOG_SOURCES += $(PWD)/rtmc_tb.sv
COMPILE_ARGS    += -I$(SRC_DIR)

TOPLEVEL = rtmc_tb
MODULE   = rtmc_scan_test

endif

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
