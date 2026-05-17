/*
 * Copyright (c) 2024 J. R. Petrus
 * SPDX-License-Identifier: Apache-2.0
 */

// Scan chain total: 373 bits
//   [0..88]   rtmc_spi (includes rtmc_spi_rxtx): 89 bits
//   [89..230] rtmc_ctrl ctrl_1: 142 bits
//   [231..372] rtmc_ctrl ctrl_2: 142 bits
//
// The reset synchronizer FFs (meta_rst_n, sync_rst_n) are intentionally
// excluded from the scan chain: shifting scan data into them would corrupt
// sync_rst_n and reset all downstream logic during scan shifting.

module rtmc_core #(
    parameter ADDR_W = 8,
    parameter DATA_W = 16,
    parameter MC_W = 8
)
(
    input  logic clk,
    input  logic rst_n,

    // SPI interface.
    input  logic sck,
    input  logic cs_n,
    input  logic sdi,
    output logic sdo,

    // GPIO.
    input  logic [3:0] gpi,
    output logic [3:0] gpo,

    // Stepper motors.
    output logic [MC_W-1:0] mc,
    output logic [MC_W-1:0] mc_oe,

    // Scan chain
    input  logic scan_en,
    input  logic scan_in,
    output logic scan_out
);
    // Reset synchronization.
    logic meta_rst_n;
    logic sync_rst_n;

    // Register bus.
    logic [ADDR_W-1:0] reg_addr;
    logic [DATA_W-1:0] reg_wdat;
    logic reg_wr;
    logic reg_rd;
    logic [DATA_W-1:0] reg_rdat;
    logic reg_ack;

    // Per-controller register bus signals.
    logic reg_wr_0, reg_wr_1;
    logic reg_rd_0, reg_rd_1;
    logic [DATA_W-1:0] reg_rdat_0, reg_rdat_1;
    logic reg_ack_0, reg_ack_1;
    logic [MC_W/2-1:0] mc_0, mc_1;
    logic [MC_W/2-1:0] mc_oe_0, mc_oe_1;
    logic [3:0] gpo_0, gpo_1;

    // Scan chain intermediates between sub-modules.
    logic sc_spi_out;
    logic sc_ctrl1_out;

    // Address bits [7:5] select which controller handles the transaction.
    assign reg_wr_0 = reg_wr & (reg_addr[7:5] == 3'h0);
    assign reg_wr_1 = reg_wr & (reg_addr[7:5] == 3'h1);
    assign reg_rd_0 = reg_rd & (reg_addr[7:5] == 3'h0);
    assign reg_rd_1 = reg_rd & (reg_addr[7:5] == 3'h1);

    // Mux read data and ack back to the SPI controller.
    assign reg_rdat = (reg_addr[7:5] == 3'h0) ? reg_rdat_0 :
                      (reg_addr[7:5] == 3'h1) ? reg_rdat_1 : '0;

    assign reg_ack  = (reg_addr[7:5] == 3'h0) ? reg_ack_0 :
                      (reg_addr[7:5] == 3'h1) ? reg_ack_1 : '0;

    // Concatenate outputs from both controllers.
    assign mc = {mc_1, mc_0};
    assign mc_oe = {mc_oe_1, mc_oe_0};
    assign gpo = {gpo_1, gpo_0};

    // Reset synchronizer (excluded from scan chain — see module comment).
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            meta_rst_n <= '0;
            sync_rst_n <= '0;
        end
        else begin
            meta_rst_n <= '1;
            sync_rst_n <= meta_rst_n;
        end;
    end

    rtmc_spi #(
        .ADDR_W(ADDR_W),
        .DATA_W(DATA_W)
    )
    spi(
        .clk(clk),
        .rst_n(sync_rst_n),
        .sck(sck),
        .cs_n(cs_n),
        .sdi(sdi),
        .sdo(sdo),
        .reg_addr(reg_addr),
        .reg_wdat(reg_wdat),
        .reg_wr(reg_wr),
        .reg_rd(reg_rd),
        .reg_rdat(reg_rdat),
        .reg_ack(reg_ack),
        .scan_en(scan_en),
        .scan_in(scan_in),
        .scan_out(sc_spi_out)
    );

    rtmc_ctrl #(
        .ADDR_W(5),
        .DATA_W(DATA_W),
        .MC_W(MC_W/2)
    )
    ctrl_1(
        .clk(clk),
        .rst_n(sync_rst_n),
        .reg_addr(reg_addr[4:0]),
        .reg_wdat(reg_wdat),
        .reg_wr(reg_wr_0),
        .reg_rd(reg_rd_0),
        .reg_rdat(reg_rdat_0),
        .reg_ack(reg_ack_0),
        .gpi(gpi),
        .gpo(gpo_0),
        .mc(mc_0),
        .mc_oe(mc_oe_0),
        .scan_en(scan_en),
        .scan_in(sc_spi_out),
        .scan_out(sc_ctrl1_out)
    );

    rtmc_ctrl #(
        .ADDR_W(5),
        .DATA_W(DATA_W),
        .MC_W(MC_W/2)
    )
    ctrl_2(
        .clk(clk),
        .rst_n(sync_rst_n),
        .reg_addr(reg_addr[4:0]),
        .reg_wdat(reg_wdat),
        .reg_wr(reg_wr_1),
        .reg_rd(reg_rd_1),
        .reg_rdat(reg_rdat_1),
        .reg_ack(reg_ack_1),
        .gpi(gpi),
        .gpo(gpo_1),
        .mc(mc_1),
        .mc_oe(mc_oe_1),
        .scan_en(scan_en),
        .scan_in(sc_ctrl1_out),
        .scan_out(scan_out)
    );

endmodule
