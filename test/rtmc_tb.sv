`default_nettype none
`timescale 1ns / 1ps

import rtmc_pkg::*;

/* This testbench just instantiates the module and makes some convenient wires
   that can be driven / tested by the cocotb test.py.
*/

module rtmc_tb();

  // Dump the signals to a VCD file. You can view it with gtkwave.
  initial begin
    $dumpfile("rtmc_tb.vcd");
    $dumpvars(0, rtmc_tb);
  end

  // Wire up the inputs and outputs.
  logic clk;
  logic rst_n;
  spi_if spi();
  gpio_if gpio();
  motor_if motor();

  logic [2:0] uo_dont_care;
  logic ena;

  // Scan chain control signals.
  // scan_en  = ui_in[7]: 1 = scan mode, 0 = functional mode
  // scan_in_sig drives ui_in[6] when scan_en=1; spi.mosi drives it otherwise.
  // scan_out = uo_out[4].
  logic scan_en;
  logic scan_in_sig;
  logic scan_out;

  /*
  Inputs
  ui[0]: "General Purpose Input gpi[0]"
  ui[1]: "General Purpose Input gpi[1]"
  ui[2]: "General Purpose Input gpi[2]"
  ui[3]: "General Purpose Input gpi[3]"
  ui[4]: "SPI0.cs  / scan: hold HIGH during scan"
  ui[5]: "SPI0.sck"
  ui[6]: "SPI0.tx  / scan_in (mux with SPI MOSI)"
  ui[7]: "scan_en  (0 = functional mode, 1 = scan mode)"

  Outputs
  uo[0]: "General Purpose Output gpo[0]"
  uo[1]: "General Purpose Output gpo[1]"
  uo[2]: "General Purpose Output gpo[2]"
  uo[3]: "General Purpose Output gpo[3]"
  uo[4]: "scan_out"
  uo[5]: "scan_en echo"
  uo[6]: "Connected to ena"
  uo[7]: "SPI0.rx"
  */

  // ui_in[6]: in scan mode, scan_in_sig drives it; in functional mode, spi.mosi.
  wire mosi_mux = scan_en ? scan_in_sig : spi.mosi;

  tt_um_rtmc_top_jrpetrus dut(
      // Include power ports for the Gate Level test:
`ifdef GL_TEST
      .VPWR(1'b1),
      .VGND(1'b0),
`endif
      .ui_in({scan_en, mosi_mux, spi.sclk, spi.cs, gpio.gpi}),
      .uo_out({spi.miso, uo_dont_care[1:0], scan_out, gpio.gpo}),
      .uio_in(8'd0),
      .uio_out(motor.mc),
      .uio_oe(motor.mc_oe),
      .ena(ena),
      .clk(clk),
      .rst_n(rst_n)
  );

  // Defaults: scan inactive, scan_in_sig = 0.
  initial begin
    scan_en    = 1'b0;
    scan_in_sig = 1'b0;
  end

endmodule
