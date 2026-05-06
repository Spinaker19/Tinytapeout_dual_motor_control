/*
 * Copyright (c) 2024 J. R. Petrus
 * SPDX-License-Identifier: Apache-2.0
 */

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
    output logic [MC_W-1:0] mc_oe
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

    // Signaux de chip select
    logic reg_wr_0, reg_wr_1;
    logic reg_rd_0, reg_rd_1;
    logic [DATA_W-1:0] reg_rdat_0, reg_rdat_1;
    logic reg_ack_0, reg_ack_1;
    logic [MC_W/2-1:0] mc_0, mc_1;
    logic [MC_W/2-1:0] mc_oe_0, mc_oe_1;
    logic [3:0] gpo_0, gpo_1;

    // Multiplexage sur bits [7:5] de l'adresse
    assign reg_wr_0 = reg_wr & (reg_addr[7:5] == 3'h0);
    assign reg_wr_1 = reg_wr & (reg_addr[7:5] == 3'h1);
    assign reg_rd_0 = reg_rd & (reg_addr[7:5] == 3'h0);
    assign reg_rd_1 = reg_rd & (reg_addr[7:5] == 3'h1);

    // Multiplexage des réponses
    assign reg_rdat = (reg_addr[7:5] == 3'h0) ? reg_rdat_0 : 
                      (reg_addr[7:5] == 3'h1) ? reg_rdat_1 : '0; // Ajoute un : '0 à la fin

    assign reg_ack  = (reg_addr[7:5] == 3'h0) ? reg_ack_0 : 
                      (reg_addr[7:5] == 3'h1) ? reg_ack_1 : '0; // Ajoute un : '0 à la fin

    // Combinaison des sorties
    assign mc = {mc_1, mc_0};
    assign mc_oe = {mc_oe_1, mc_oe_0};
    assign gpo = {gpo_1, gpo_0};

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
        .rst_n(sync_rst_n),
        .*
    );

    rtmc_ctrl #(
        .ADDR_W(5),
        .DATA_W(DATA_W),
        .MC_W(MC_W/2)
    )
    ctrl_1(
        .clk(clk),
        .rst_n(sync_rst_n),
        .reg_addr(reg_addr[4:0]),     // Bits bas seulement
        .reg_wdat(reg_wdat),
        .reg_wr(reg_wr_0),             // Actif seulement si bits[7:5]==0
        .reg_rd(reg_rd_0),
        .reg_rdat(reg_rdat_0),
        .reg_ack(reg_ack_0),
        .gpi(gpi),
        .gpo(gpo_0),
        .mc(mc_0),
        .mc_oe(mc_oe_0)
    );

    rtmc_ctrl #(
        .ADDR_W(5),
        .DATA_W(DATA_W),
        .MC_W(MC_W/2)
    )
    ctrl_2(
        .clk(clk),
        .rst_n(sync_rst_n),
        .reg_addr(reg_addr[4:0]),     // Bits bas seulement
        .reg_wdat(reg_wdat),
        .reg_wr(reg_wr_1),             // Actif seulement si bits[7:5]==1
        .reg_rd(reg_rd_1),
        .reg_rdat(reg_rdat_1),
        .reg_ack(reg_ack_1),
        .gpi(gpi),
        .gpo(gpo_1),
        .mc(mc_1),
        .mc_oe(mc_oe_1)
    );

endmodule
