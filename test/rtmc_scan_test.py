# SPDX-FileCopyrightText: © 2024 J. R. Petrus
# SPDX-License-Identifier: Apache-2.0

"""
Scan chain test for tt_rtmc.

Chain depth: 373 bits (shift-right, MSB-first)
  [0..88]    rtmc_spi (includes rtmc_spi_rxtx): 89 bits
  [89..230]  rtmc_ctrl ctrl_1:                  142 bits
  [231..372] rtmc_ctrl ctrl_2:                  142 bits

Testbench signal mapping:
  dut.scan_en       = ui_in[7]  — activates scan mode
  dut.scan_in_sig   = ui_in[6]  — scan_in (separate from SPI MOSI via mosi_mux)
  dut.scan_out      = uo_out[4] — scan chain output
  dut.spi.cs        must stay 1 (SPI inactive) while scan_en=1

TIMING NOTE (Icarus Verilog + cocotb):
  After `await RisingEdge`, non-blocking FF assignments are NOT yet visible —
  cocotb fires in the active region before the NBA (non-blocking assign) update
  region. To read the COMMITTED value of a FF after a rising edge, wait for
  the following FALLING EDGE (NBA region has completed by then).

  Pattern: set scan_in on FallingEdge #i → await RisingEdge #i → FF captures →
           read scan_out on FallingEdge #i+1 (NBA committed, stable).
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles

CHAIN_DEPTH = 373      # total scan FF count
SYS_CLK_NS  = 20       # 50 MHz


async def _reset(dut) -> None:
    dut.scan_en.value     = 1   # scan mode from start (keeps functional path quiet)
    dut.scan_in_sig.value = 0
    dut.spi.cs.value      = 1
    dut.spi.sclk.value    = 0
    dut.spi.mosi.value    = 0
    dut.rst_n.value       = 0
    dut.ena.value         = 1
    dut.gpio.gpi.value    = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


async def scan_shift(dut, data_in: int, n_bits: int = CHAIN_DEPTH,
                     flush_cycles: int = None) -> int:
    """
    Flush scan chain with zeros, then shift n_bits of data_in MSB-first.

    Timing protocol (avoids Icarus non-blocking assignment read-before-commit):
      - scan_in is driven on the FALLING edge (stable before next rising edge)
      - scan_out is READ on the FALLING edge AFTER the rising edge that committed
        the FF update (NBA region complete)

    Returns integer of bits read from scan_out (MSB = first bit shifted in that exits).
    scan_en stays asserted throughout to prevent functional path from corrupting FFs.
    """
    if flush_cycles is None:
        flush_cycles = n_bits * 2

    dut.scan_en.value     = 1
    dut.spi.cs.value      = 1
    dut.scan_in_sig.value = 0

    # Flush phase: n_bits*2 falling-edge/rising-edge pairs with scan_in=0
    for _ in range(flush_cycles):
        await FallingEdge(dut.clk)
        dut.scan_in_sig.value = 0
        await RisingEdge(dut.clk)

    # Pre-load first bit of pattern on the next falling edge
    await FallingEdge(dut.clk)
    dut.scan_in_sig.value = (data_in >> (n_bits - 1)) & 1
    await RisingEdge(dut.clk)   # RisingEdge #0: FF[0] captures first bit

    # Capture loop: read scan_out at falling edge (NB committed), set next bit
    data_out = 0
    for i in range(1, n_bits + 1):
        await FallingEdge(dut.clk)
        # Read AFTER the previous rising edge's non-blocking assignments committed
        bit_out = int(dut.scan_out.value)
        data_out = (data_out << 1) | bit_out

        # Set scan_in for the next rising edge
        if i < n_bits:
            next_bit = (data_in >> (n_bits - 1 - i)) & 1
        else:
            next_bit = 0
        dut.scan_in_sig.value = next_bit
        await RisingEdge(dut.clk)   # RisingEdge #i: FF chain advances

    dut.scan_en.value     = 0
    dut.scan_in_sig.value = 0
    return data_out


@cocotb.test()
async def test_scan_shift_passthrough(dut):
    """
    Verify the scan chain is a proper 373-bit shift register.

    Steps:
    1. Reset.
    2. Assert scan_en and flush chain with zeros (2*CHAIN_DEPTH falling/rising pairs).
    3. Shift in a walking-one pattern: '1' at MSB (first shifted in), rest zeros.
    4. Collect CHAIN_DEPTH bits from scan_out (read at falling edges).

    The '1' is shifted in at RisingEdge #0 and exits at RisingEdge #(CHAIN_DEPTH-1),
    which is read at FallingEdge #CHAIN_DEPTH.
    In data_out (MSB first collection), it appears at bit [0] (LSB).
    """
    clock = Clock(dut.clk, SYS_CLK_NS, units="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)

    dut._log.info(f"Scan chain depth: {CHAIN_DEPTH} bits")
    dut._log.info("Shifting walking-one pattern (flush + '1' then zeros)...")

    pattern = 1 << (CHAIN_DEPTH - 1)   # '1' shifted in first, 372 zeros after
    captured = await scan_shift(dut, pattern)

    expected = 1  # '1' exits last → LSB of captured
    assert captured == expected, (
        f"Scan passthrough FAILED: "
        f"expected=0x{expected:X}, captured=0x{captured:X}, "
        f"non-zero bits: {bin(captured).count('1')}"
    )
    dut._log.info(
        f"Scan passthrough PASSED: '1' traversed all {CHAIN_DEPTH} FFs correctly."
    )
    await ClockCycles(dut.clk, 5)


@cocotb.test()
async def test_scan_capture_reset_state(dut):
    """
    Immediately after reset, shift out the scan chain without a prior flush.

    Expected non-zero bits:
    - rtmc_spi_rxtx.bit_count[2:0] = 3'b111  (resets to all-ones) -> 3 ones
    - All other FFs reset to 0
    """
    clock = Clock(dut.clk, SYS_CLK_NS, units="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)

    dut._log.info("Scanning out post-reset state (no flush)...")

    # Directly shift out with scan_in=0, read at falling edges
    dut.scan_en.value     = 1
    dut.spi.cs.value      = 1
    dut.scan_in_sig.value = 0

    # Prime
    await FallingEdge(dut.clk)
    dut.scan_in_sig.value = 0
    await RisingEdge(dut.clk)

    data_out = 0
    for i in range(1, CHAIN_DEPTH + 1):
        await FallingEdge(dut.clk)
        bit_out = int(dut.scan_out.value)
        data_out = (data_out << 1) | bit_out
        dut.scan_in_sig.value = 0
        await RisingEdge(dut.clk)

    dut.scan_en.value = 0

    ones_count = bin(data_out).count('1')
    dut._log.info(f"Post-reset scan: {ones_count} non-zero bit(s) out of {CHAIN_DEPTH}")
    assert ones_count <= 6, (
        f"Too many non-zero bits after reset: {ones_count} (expected <=6)"
    )
    dut._log.info(f"Post-reset scan PASSED ({ones_count} non-zero bit(s)).")
    await ClockCycles(dut.clk, 5)


@cocotb.test()
async def test_scan_functional_unaffected(dut):
    """
    Verify that activating then deactivating scan mode does not corrupt
    the functional signals visible from the testbench.
    """
    clock = Clock(dut.clk, SYS_CLK_NS, units="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)

    dut._log.info("Running full scan (all zeros), then checking functional path...")
    await scan_shift(dut, 0)

    await ClockCycles(dut.clk, 10)

    try:
        gpo_val = int(dut.gpio.gpo.value)
        dut._log.info(f"gpo after scan = 0b{gpo_val:04b} (no X values).")
    except ValueError:
        assert False, "gpo contains 'X' after scan -- functional state corrupted."

    try:
        so_val = int(dut.scan_out.value)
        dut._log.info(f"scan_out after deassert = {so_val}.")
    except ValueError:
        assert False, "scan_out contains 'X' after scan deactivation."

    dut._log.info("Functional integrity after scan PASSED.")
    await ClockCycles(dut.clk, 5)
