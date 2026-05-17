/*
 * Copyright (c) 2024 J. R. Petrus
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

/*
Inputs
ui[0]: "General Purpose Input gpi[0]"
ui[1]: "General Purpose Input gpi[1]"
ui[2]: "General Purpose Input gpi[2]"
ui[3]: "General Purpose Input gpi[3]"
ui[4]: "SPI0.cs  / scan: hold HIGH during scan"
ui[5]: "SPI0.sck"
ui[6]: "SPI0.tx  / scan_in (mux: SPI MOSI when cs=0, scan_in when scan_en=1 & cs=1)"
ui[7]: "scan_en  (1 = scan mode, 0 = functional mode)"

Outputs
uo[0]: "General Purpose Output gpo[0]"
uo[1]: "General Purpose Output gpo[1]"
uo[2]: "General Purpose Output gpo[2]"
uo[3]: "General Purpose Output gpo[3]"
uo[4]: "scan_out (scan chain output)"
uo[5]: "scan_en echo (= ui[7])"
uo[6]: "Connected to ena"
uo[7]: "SPI0.rx"

Bidirectional pins
uio[0]: "Motor Control mc[0]"
uio[1]: "Motor Control mc[1]"
uio[2]: "Motor Control mc[2]"
uio[3]: "Motor Control mc[3]"
uio[4]: "Motor Control mc[4]"
uio[5]: "Motor Control mc[5]"
uio[6]: "Motor Control mc[6]"
uio[7]: "Motor Control mc[7]"

Scan chain protocol (373 bits, shift-right, MSB-first):
  ui[7]  = scan_en : assert to enter scan mode (keep cs=ui[4]=1)
  ui[6]  = scan_in : drive scan data on each rising clk edge
  uo[4]  = scan_out: read scan output on each rising clk edge
  Chain depth: 373 bits (89 SPI + 142 ctrl_1 + 142 ctrl_2)
*/

module tt_um_rtmc_top_jrpetrus (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
    wire scan_out_w;

    assign uo_out[6] = ena;
    assign uo_out[5] = ui_in[7];   // echo scan_en
    assign uo_out[4] = scan_out_w; // scan chain output

    rtmc_core core(
        .clk(clk),
        .rst_n(rst_n),
        .sck(ui_in[5]),
        .cs_n(ui_in[4]),
        .sdi(ui_in[6]),
        .sdo(uo_out[7]),
        .gpi(ui_in[3:0]),
        .gpo(uo_out[3:0]),
        .mc(uio_out),
        .mc_oe(uio_oe),
        .scan_en(ui_in[7]),
        .scan_in(ui_in[6]),
        .scan_out(scan_out_w)
    );

endmodule
